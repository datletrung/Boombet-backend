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
    except Exception as e:
        return False, "Invalid request! (1010)"

    if action == "signin":
        try:
            username = parser["username"]
            password = parser["password"]
        except:
            return False, "Invalid request! (1020-1)"

        status, conn = connect(db_host, db_usr, db_pwd, db_name)
        if not status:
            return False, "Database Error! " + str(conn)
        
        with conn.cursor() as cursor:
            query = "SELECT UA.`user_id`\
                        ,U.`display_name`\
                    FROM `UM_USER_ACC` UA\
                        ,`UM_USER` U\
                    WHERE 1=1\
                        AND UA.`user_id` = U.`user_id`\
                        AND LOWER(UA.`username`) = LOWER(%s)\
                        AND UA.`password` = %s"
            
            cursor.execute(query, [username, password])
            response = cursor.fetchall()
            if not response:
                return True, 'User ID or Password is incorrect!'

            user_id = response[0]['user_id']
            display_name = response[0]['display_name']

            verify_code = get_string(128)
            query = "UPDATE `UM_USER_ACC`\
                    SET `verify_code` = %s\
                        ,`last_login` = NOW()\
                    WHERE `user_id` = %s"
            
            cursor.execute(query, [verify_code, user_id])
            conn.commit()

            return True, {
                'user_id': str(user_id),
                'username': str(username),
                'display_name': str(display_name),
                'verify_code': str(verify_code)
            }
    elif action == "signup":
        return True, "Success!"
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