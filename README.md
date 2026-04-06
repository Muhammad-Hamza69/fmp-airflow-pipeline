# Architecture Diagram

<img width="1959" height="912" alt="image" src="https://github.com/user-attachments/assets/1217bd59-52e4-4add-8281-74ac4b9561d1" />

## EC2 Setup

- first set ec2 using a t2.large machine with 16 gb storage set inbound rules and give a port range of 4333-38888 
- ssh -i "kp-scd-warehousing-mhs.pem" ec2-user@ec2-54-205-190-33.compute-1.amazonaws.com -L 8080:localhost:8080
- mkdir docker-exp
- cd docker-exp
- curl -LfO 'https://airflow.apache.org/docs/apache-airflow/stable/docker-compose.yaml'

## Installation Command of Docker in EC2

- sudo yum update -y
- sudo yum install docker
- sudo yum install -y libxcrypt-compat
- sudo curl -L "https://github.com/docker/compose/releases/download/1.29.1/docker-compose-$(uname -s)-$(uname -m)" -o /usr/local/bin/docker-compose
- sudo chmod +x /usr/local/bin/docker-compose
- sudo gpasswd -a $USER docker
- newgrp docker
- sudo systemctl start docker
- docker-compose up -d

## Airflow Setup

- http://localhost:8080/

- Variable: In Airflow set variable of api key, user credentials and SNS arn
- Connections: In Airflow set connections of S3, and Snowflake
