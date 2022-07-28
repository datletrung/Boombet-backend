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
    except Exception as e:
        return False, "Invalid request! (1010)"

    if action == "new":
        try:
            side = parser["side"]
            user_id = str(parser["user_id"])
            verify_code = parser["verify_code"]
            amount = str(parser["amount"])
        except:
            return False, "Invalid request! (1020-1)"
        
        if side != "0" and side != "1":
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
                    FROM `CORE_RANDOM_SEED`\
                    WHERE `date` = STR_TO_DATE(%s, '%%Y-%%m-%%d')"

            cursor.execute(query, [today])
            response = cursor.fetchall()

            if not response:
                return False, "Daily seed not found!"
            
            random_seed = response[0]['random_seed']
            
            
            #----------CHECK USER ID VALID
            query = "SELECT *\
                    FROM `UM_USER` U\
                        ,`UM_USER_ACC` UA\
                    WHERE 1=1\
                        AND UA.`user_id` = U.`user_id`\
                        AND UA.`user_id` = %s\
                        AND UA.`verify_code` = %s"

            cursor.execute(query, [user_id, verify_code])
            response = cursor.fetchall()
            
            if not response:
                return True, 'Failed to verify User ID!'


            #----------GET CLIENT SEED
            query = "SELECT `client_seed`\
                    FROM `UM_USER`\
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
            query = "INSERT INTO `G_CF_BET` (`amount`, `random_seed`, `result`, `effective_date`)\
                    VALUES(%s, %s, %s, NOW())"
            
            cursor.execute(query, [amount, random_seed, result])
            conn.commit()

            #----------SELECT BET ID
            query = "SELECT `bet_id`\
                    FROM `G_CF_BET`\
                    WHERE `amount` = %s\
                        AND `random_seed` = %s\
                        AND `result` = %s"
            
            cursor.execute(query, [amount, random_seed, result])
            response = cursor.fetchall()

            if not response:
                return False, "Internal Server Error!"

            bet_id = response[0]['bet_id']

            #----------INSERT BET USER
            query = "INSERT INTO `G_CF_USER`(`bet_id`, `user_id`, `side`, `effective_date`)\
                    VALUES(%s, %s, %s, NOW())"
            
            cursor.execute(query, [bet_id, user_id, side])
            conn.commit()

            return True, {
                'bet_id': str(bet_id),
                'user_id': str(user_id),
                'side': str(side)
            }


    elif action == "join":
        try:
            user_id = str(parser["user_id"])
            verify_code = parser["verify_code"]
            bet_id = str(parser["bet_id"])
        except:
            return False, "Invalid request! (1020-2)"

        status, conn = connect(db_host, db_usr, db_pwd, db_name)
        if not status:
            return False, "Database Error! " + str(conn)
        
        with conn.cursor() as cursor:
            #----------CHECK USER ID VALID
            query = "SELECT *\
                    FROM `UM_USER` U\
                        ,`UM_USER_ACC` UA\
                    WHERE 1=1\
                        AND UA.`user_id` = U.`user_id`\
                        AND UA.`user_id` = %s\
                        AND UA.`verify_code` = %s"

            cursor.execute(query, [user_id, verify_code])
            response = cursor.fetchall()
            
            if not response:
                return True, 'Failed to verify User ID!'

            #----------GET OPPOSITE SIDE
            query = "SELECT CB.`bet_id`\
                            ,CB.`amount`\
                            ,CU.`user_id`\
                            ,CU.`side`\
                    FROM `G_CF_BET` CB\
                        ,`G_CF_USER` CU\
                    WHERE 1=1\
                        AND CB.`bet_id` = %s\
                        AND CU.`bet_id` = CB.`bet_id`\
                        AND 1 = (\
                            SELECT COUNT(CU.`bet_id`)\
                            FROM `G_CF_USER` CU\
                            WHERE CB.`bet_id` = CU.`bet_id`\
                        )"
            cursor.execute(query, [bet_id])
            response = cursor.fetchall()
            if not response:
                return True, "Bet ID does not exist or has been expired!"
            
            side = response[0]['side']
            side = '0' if side == '1' else '1'

            #----------INSERT INTO USER BET
            query = "INSERT INTO `G_CF_USER` (`bet_id`, `user_id`, `side`, `effective_date`)\
                    SELECT * FROM (\
                        SELECT %s as `bet_id`\
                            ,%s as `user_id`\
                            ,%s as `side`\
                            ,NOW() as `effective_date`\
                    ) AS tmp\
                    WHERE EXISTS (\
                        SELECT 1\
                        FROM `G_CF_BET` CB\
                            ,`G_CF_USER` CU\
                        WHERE 1=1\
                            AND CB.`bet_id` = %s\
                            AND CU.`bet_id` = CB.`bet_id`\
                            AND 1 = (\
                                SELECT COUNT(CU.`bet_id`)\
                                FROM `G_CF_USER` CU\
                                WHERE CB.`bet_id` = CU.`bet_id`\
                            )\
                    )"
            cursor.execute(query, [bet_id, user_id, side, bet_id])
            conn.commit()

            #----------CHECK IF USER JOIN BET
            query = "SELECT CB.`result`\
                    FROM `G_CF_BET` CB\
                        ,`G_CF_USER` CU\
                    WHERE 1=1\
                        AND CB.`bet_id` = %s\
                        AND CU.`bet_id` = CB.`bet_id`\
                        AND CU.`user_id` = %s\
                        AND 2 = (\
                            SELECT COUNT(CU.`bet_id`)\
                            FROM `G_CF_USER` CU\
                            WHERE CB.`bet_id` = CU.`bet_id`\
                        )"
            cursor.execute(query, [bet_id, user_id])
            response = cursor.fetchall()

            if not response:
                return True, "Bet ID does not exist or has been expired!"

            return True, {'result': str(response[0]['result'])}
            

    
    elif action == "get":
        #----------GET EXISTING BET
        status, conn = connect(db_host, db_usr, db_pwd, db_name)
        if not status:
            return False, "Database Error! " + str(conn)
        
        with conn.cursor() as cursor:
            query = "SELECT CB.`bet_id`\
                            ,CB.`amount`\
                            ,CU.`user_id`\
                            ,CU.`side`\
                            ,U.`display_name`\
                    FROM `G_CF_BET` CB\
                        ,`G_CF_USER` CU\
                        ,`UM_USER` U\
                    WHERE 1=1\
                        AND CU.`bet_id` = CB.`bet_id`\
                        AND U.`user_id` = CU.`user_id`\
                        AND 1 = (\
                            SELECT COUNT(CU.`bet_id`)\
                            FROM `G_CF_USER` CU\
                            WHERE CB.`bet_id` = CU.`bet_id`\
                        )"
            cursor.execute(query, [])
            response = cursor.fetchall()

            if not response:
                return True, "No existing bet!"
            
            data = []
            for res in response:
                data.append({
                            'bet_id': str(res['bet_id']),
                            'user_id': str(res['user_id']),
                            'side': str(res['side']),
                            'amount': str(res['amount']),
                            'display_name': str(res['display_name'])
                })

            return True, data
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