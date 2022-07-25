import os
import json
import time
import boto3
import random
import string
import pymysql

def get_string(length):
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
    parser = json.loads(event["body"])["data"]
    #parser = event["body"]

    try:
        action = parser["action"]
        user_id = parser["user_id"]
    except Exception as e:
        return False, "Invalid request! (1010)"

    if action == "new":
        try:
            side = parser["side"]
        except:
            return False, "Invalid request! (1020-1)"

        status, conn = connect(db_host, db_usr, db_pwd, db_name)
        if not status:
            return False, "Database Error! " + str(conn)

        return True, "Place new Bet for '" + str(side) + "' at " + str(time.time())
    elif action == "join":
        try:
            bet_id = parser["bet_id"]
        except:
            return False, "Invalid request! (1020-2)"
        return True, "Join existing Bet for '" + str(bet_id) + "' at " + str(time.time())
    else:
        return False, "Invalid request! (1020-3)"

    

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