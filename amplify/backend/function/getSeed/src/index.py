import os
import json
import boto3
import pymysql
import datetime

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
    select_all = False

    try:
        date = str(parser['date'])
        if date.upper() == "ALL":
            raise Exception("Extract ALL")
        try:
            date = date[:4] + "-" + date[4:6]  + "-" + date[6:] 
            regex = datetime.datetime.strptime
            assert regex(date, '%Y-%m-%d')
        except:
            return False, "Wrong date format!"
    except Exception as e:
        if str(e) == "Extract ALL":
            select_all = True
        else:
            date = datetime.date.today().strftime("%Y-%m-%d")

    status, conn = connect(db_host, db_usr, db_pwd, db_name)
    if not status:
        return False, "Database Error!"

    with conn.cursor() as cursor:
        today = datetime.date.today().strftime("%Y-%m-%d")
        query = "SELECT `date`,\
                        (CASE WHEN `date` >= STR_TO_DATE(%s, '%%Y-%%m-%%d')\
                        THEN `masked_seed`\
                        ELSE `random_seed`\
                        END\
                        ) AS `seed`,\
                        `hashed_seed`,\
                        `generated_time`\
                FROM `random_seed`"

        if not select_all:      #------------SELECT only 1 specific date
            query += "WHERE STR_TO_DATE(%s, '%%Y-%%m-%%d') = `date`"
            cursor.execute(query, [today, date])
            response = cursor.fetchall()

            if not response and date == datetime.date.today().strftime("%Y-%m-%d"):
                return False, "Daily seed not found!"
            elif not response:
                return False, "Database Error!"

            return True, [{'date':str(response[0]['date']),
                          'seed':response[0]['seed'],
                          'hashed_seed':response[0]['hashed_seed'],
                          'generated_time':str(response[0]['generated_time'])
                         }]
        else:                   #------------SELECT all historical data
            query += "ORDER BY `date` DESC"
            cursor.execute(query, [today])
            response = cursor.fetchall()

            if not response:
                return True, "No seed was found!"

            data = []

            today_seed_exist = False
            for res in response:
                if str(res['date']) == datetime.date.today().strftime("%Y-%m-%d"):
                    today_seed_exist = True
                data.append({
                    'date':str(res['date']),
                    'seed':res['seed'],
                    'hashed_seed':res['hashed_seed'],
                    'generated_time':str(res['generated_time'])
                })
            if not today_seed_exist:
                return False, "Daily seed not found!"
            return True, data

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