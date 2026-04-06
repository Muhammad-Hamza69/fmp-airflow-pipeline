from airflow import DAG
from airflow.decorators import task
from airflow.providers.amazon.aws.hooks.s3 import S3Hook
from airflow.providers.snowflake.hooks.snowflake import SnowflakeHook
from airflow.providers.amazon.aws.hooks.base_aws import AwsBaseHook
from airflow.models import Variable
from datetime import datetime, timedelta
import requests
import json

# Config
SYMBOLS = ["AAPL", "MSFT", "GOOGL", "AMZN", "TSLA"]
S3_BUCKET = "airflow-bucket-mhs"
S3_PREFIX = "raw/"

default_args = {
    'owner': 'airflow',
    'depends_on_past': False,
    'email_on_failure': False,
    'retries': 1,
    'retry_delay': timedelta(minutes=1)
}

with DAG(
    dag_id="fmp_profile_s3_to_snowflake",
    default_args=default_args,
    start_date=datetime(2026, 4, 5),
    schedule="@daily",
    catchup=False
) as dag:

    @task()
    def fetch_and_upload_s3():
        API_KEY = Variable.get("FMP_API_KEY")
        s3 = S3Hook(aws_conn_id="my_s3_conn")

        for symbol in SYMBOLS:
            url = f"https://financialmodelingprep.com/stable/profile?symbol={symbol}&apikey={API_KEY}"
            response = requests.get(url)
            if response.status_code == 200:
                data = response.json()
                s3_key = f"{S3_PREFIX}{symbol}.json"
                s3.load_string(
                    string_data=json.dumps(data, indent=2),
                    key=s3_key,
                    bucket_name=S3_BUCKET,
                    replace=True
                )
                print(f"Uploaded {symbol} to S3 at {s3_key}")
            else:
                raise Exception(f"Failed to fetch {symbol}: {response.text}")

    @task()
    def load_s3_to_snowflake():
        s3 = S3Hook(aws_conn_id="my_s3_conn")
        sf = SnowflakeHook(snowflake_conn_id="my_snowflake_conn")
        conn = sf.get_conn()
        cursor = conn.cursor()

        # Explicitly set Snowflake context
        cursor.execute("USE WAREHOUSE COMPUTE_WH")
        cursor.execute("USE DATABASE FMP_DB")
        cursor.execute("USE SCHEMA FMP_schema")

        keys = s3.list_keys(bucket_name=S3_BUCKET, prefix=S3_PREFIX)
        if not keys:
            print("No JSON files found in S3.")
            return

        # Filter only .json files
        json_keys = [k for k in keys if k.endswith(".json")]
        print(f"Found {len(json_keys)} JSON files: {json_keys}")

        inserted_count = 0
        for key in json_keys:
            data_str = s3.read_key(key=key, bucket_name=S3_BUCKET)
            data_json = json.loads(data_str)

            symbol = key.replace(S3_PREFIX, "").replace(".json", "")
            records = data_json if isinstance(data_json, list) else [data_json]

            for item in records:
                symbol_val = item.get("symbol", symbol)
                json_str = json.dumps(item)

                insert_sql = """
                    INSERT INTO STOCK_PROFILES (SYMBOL, PROFILE)
                    SELECT %s, PARSE_JSON(%s)
                """
                cursor.execute(insert_sql, (symbol_val, json_str))
                inserted_count += 1
                print(f"Inserted record for symbol: {symbol_val}")

        conn.commit()
        cursor.close()
        conn.close()
        print("All records inserted successfully.")

        # Return summary for SNS notification
        return {
            "files_processed": len(json_keys),
            "records_inserted": inserted_count,
            "symbols": [k.replace(S3_PREFIX, "").replace(".json", "") for k in json_keys]
        }

    @task()
    def send_sns_notification(snowflake_result: dict):
        SNS_TOPIC_ARN = Variable.get("SNS_TOPIC_ARN").strip()
        print(f"DEBUG - SNS_TOPIC_ARN: '{SNS_TOPIC_ARN}'")

        aws_hook = AwsBaseHook(aws_conn_id="my_s3_conn", client_type="sns")
        sns_client = aws_hook.get_client_type(region_name="us-west-2")  # ✅ your region

        files_processed = snowflake_result.get("files_processed", 0)
        records_inserted = snowflake_result.get("records_inserted", 0)
        symbols = snowflake_result.get("symbols", [])
        run_date = datetime.now().strftime("%Y-%m-%d %H:%M:%S")

        subject = "Airflow DAG Success: fmp_profile_s3_to_snowflake"
        message = f"""
        DAG Run Summary
        ===============================
        DAG Name      : fmp_profile_s3_to_snowflake
        Status        : SUCCESS
        Run Date      : {run_date}
        ===============================
        Task 1 - fetch_and_upload_s3   : SUCCESS
        Task 2 - load_s3_to_snowflake  : SUCCESS
        ===============================
        Summary:
        - Symbols Processed : {symbols}
        - Files Processed   : {files_processed}
        - Records Inserted  : {records_inserted}
        - Snowflake Table   : FMP_DB.FMP_schema.STOCK_PROFILES
        ===============================
        """

        response = sns_client.publish(
            TopicArn=SNS_TOPIC_ARN,
            Subject=subject,
            Message=message
        )
        print(f"SNS notification sent successfully. MessageId: {response['MessageId']}")

    # DAG flow
    upload_task = fetch_and_upload_s3()
    snowflake_task = load_s3_to_snowflake()
    sns_task = send_sns_notification(snowflake_task)

    upload_task >> snowflake_task >> sns_task
