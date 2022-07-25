import os
import json
import time
import boto3
import random
import string
import pymysql
import datetime

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
        amount = str(parser["amount"])
    except Exception as e:
        return False, "Invalid request! (1010)"

    if action == "new":
        try:
            side = parser["side"]
        except:
            return False, "Invalid request! (1020-1)"
        
        if side not in range(0,2):
            return False, "Invalid request! (1030)"
        
        side = str(side)

        status, conn = connect(db_host, db_usr, db_pwd, db_name)
        if not status:
            return False, "Database Error! " + str(conn)
        
        with conn.cursor() as cursor:
            #----------GET DATE AND TIME
            today = datetime.date.today().strftime("%Y-%m-%d")
            current_time = str(time.time()).replace('.', '')
            if len(current_time) <= 16:
                current_time += '0'*(16-len(current_time))
            else:
                current_time = current_time[:16]
            
            #----------GET RANDOM SEED
            query = "SELECT `random_seed`\
                    FROM `random_seed`\
                    WHERE `date` = STR_TO_DATE(%s, '%%Y-%%m-%%d')"

            cursor.execute(query, [today])
            response = cursor.fetchall()

            if not response:
                return False, "Daily seed not found!"
            
            random_seed = response[0]['random_seed']
            
            #----------GET CLIENT SEED
            query = "SELECT `client_seed`\
                    FROM `user`\
                    WHERE `user_id` = %s"

            cursor.execute(query, [user_id])
            response = cursor.fetchall()
            
            if not response:
                client_seed = get_string(32)
            else:
                client_seed = response[0]['client_seed']

            #----------CREATE BET SEED
            random_seed = client_seed[:len(client_seed)//2] + random_seed + client_seed[len(client_seed)//2+1:]
            random_seed = current_time[:len(current_time)//2] + random_seed + current_time[len(current_time)//2+1:]
            random_seed = random_seed.replace(' ','')
            random.seed(random_seed)
            result = str(random.randint(0,1))


            #----------INSERT BET SEED
            query = "INSERT INTO `coinflip_bet` (`amount`, `random_seed`, `result`, `timestamp`)\
                    VALUES(%s, %s, %s, NOW())"
            
            cursor.execute(query, [amount, random_seed, result])
            conn.commit()

            #----------SELECT BET ID
            query = "SELECT `bet_id`\
                    FROM `coinflip_bet`\
                    WHERE `amount` = %s\
                        AND `random_seed` = %s\
                        AND `result` = %s"
            
            cursor.execute(query, [amount, random_seed, result])
            response = cursor.fetchall()

            if not response:
                return False, "Internal Server Error!"

            bet_id = response[0]['bet_id']

            #----------INSERT BET USER
            query = "INSERT INTO `coinflip_user`(`bet_id`, `user_id`, `side`, `timestamp`)\
                    VALUES(%s, %s, %s, NOW())"
            
            cursor.execute(query, [bet_id, user_id, side])
            conn.commit()

            return True, {
                'bet_id': bet_id
            }

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