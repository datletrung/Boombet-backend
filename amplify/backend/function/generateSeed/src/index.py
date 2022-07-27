import os
import json
import time
import boto3
import random
import string
import hashlib
import pymysql
import datetime

def get_string(length):
    random.seed(str(time.time()).replace('.', ''))
    return ''.join(random.choice(string.ascii_letters + string.digits) for _ in range(length))

def get_secret():
    secret_name = os.environ["SECRET_NAME"]
    region_name = "us-east-2"

    session = boto3.session.Session()
    client = session.client(
        service_name='secretsmanager',
        region_name=region_name
    )

    try:
        response = client.get_secret_value(
            SecretId=secret_name
        )
    except Exception as e:
        raise e
    
    secret = json.loads(response['SecretString'])
    return [secret["db_host"], secret["db_usr"], secret["db_pwd"], secret["db_name"]]


def connect(db_host, db_usr, db_pwd, db_name):
    try:
        conn = pymysql.connect(host=db_host,user=db_usr,
                               passwd=db_pwd,db=db_name,
                               connect_timeout=5,
                               cursorclass=pymysql.cursors.DictCursor)
        return True, conn                       
    except Exception as e:
        return False, str(e)


def main(event):
    db_host, db_usr, db_pwd, db_name = get_secret()
    status, conn = connect(db_host, db_usr, db_pwd, db_name)
    if not status:
        return False, "Database Error!"

    with conn.cursor() as cursor:
        date = datetime.date.today().strftime("%Y-%m-%d")
        query = "SELECT count(*) AS `count`\
                FROM `CORE_RANDOM_SEED`\
                WHERE STR_TO_DATE(%s, '%%Y-%%m-%%d') = `date`"

        cursor.execute(query, [date])
        response = cursor.fetchall()

        if not response:
            return False, "Database Error!"

        if response[0]['count'] != 0:
            return True, "Seed already exists."

        #-----Check Random Seed Exist---
        while True:
            random_seed = get_string(64)
            masked_seed = random_seed[:16] + "*"*32 + random_seed[48:]
            hashed_seed = hashlib.sha256(random_seed.encode()).hexdigest()
            query = "INSERT IGNORE INTO `CORE_RANDOM_SEED` (`date`, `random_seed`, `masked_seed`, `hashed_seed`, `effective_date`)\
                        VALUES (STR_TO_DATE(%s, '%%Y-%%m-%%d'), %s, %s, %s, NOW())"

            cursor.execute(query, [date, random_seed, masked_seed, hashed_seed])
            conn.commit()

            query = "SELECT 1\
                    FROM `CORE_RANDOM_SEED`\
                    WHERE 1=1\
                        AND `random_seed` = %s\
                        AND `date` = STR_TO_DATE(%s, '%%Y-%%m-%%d')"

            cursor.execute(query, [random_seed, date])
            response = cursor.fetchall()

            if response:
                return True, "New seed generated!"
    return False, "Database Error!"
    

def handler(event, context):
    status, data = main(event)
    return {
            'statusCode': 200,
            'headers': {
                'Access-Control-Allow-Headers': 'Content-Type',
                'Access-Control-Allow-Origin': '*',
                'Access-Control-Allow-Methods': 'OPTIONS,POST,GET'
            },
            'body': json.dumps({
                                "status":status,
                                "data":data,
                    })
        }