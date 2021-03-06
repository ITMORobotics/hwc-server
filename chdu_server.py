from flask import Flask, jsonify
from flask import request, send_from_directory
import logging
import os,sys
import hashlib, pathlib

from flask_limiter import Limiter
from flask_limiter.util import get_remote_address


from auth import AuthHandler

sys.path.append(os.path.dirname(os.path.dirname(os.path.abspath(__file__))))
from task import task

def get_file_version(filename: str) -> dict:
    with open(filename,'rb') as f:
        client_bytes = f.read()
        f.close()
        return {'md5': hashlib.md5(client_bytes).hexdigest()}


def start():
    os.system('cd ../hwc-matlab-client && git pull && hmd2html -s README.md -d ../html')
    os.system('mv ../html/README.html /var/www/hdu/html/index.html')
    os.system('rm -rv ../html')
    return get_file_version('../hwc-matlab-client/CHDU.m'), get_file_version('../hwc-matlab-client/chdu_connect.m')


ATTEMPS_LIMIT = 40
MATLAB_CLIENT_VERSION, MATLAB_LAUNCHER_VERSION = start()

auth = AuthHandler('auth_manager_config.json')
task_list = (task.Task('server_task_data/lab1_tasks.json'), task.Task('server_task_data/lab2_tasks.json'), task.Task('server_task_data/lab3_tasks.json'), task.Task('server_task_data/lab4_tasks.json'), task.Task('server_task_data/lab5_tasks.json'), task.Task('server_task_data/lab6_tasks.json'))

app = Flask(__name__)
limiter = Limiter(
    app,
    key_func=get_remote_address,
    default_limits=["400 per day", "100 per hour", "1 per second"]
)

@app.route('/api/ok', methods=['GET'])
def ok():
    return jsonify(isError= False, message= "OK", statusCode=200, data='')

@app.route('/api/register', methods=['POST'])
def register():
    content_type = request.headers.get('Content-Type')
    if 'application/json' in content_type:
        user_data = request.json['auth']
        code, msg = auth.register(user_data)
        return jsonify(isError=(code!=200), message=msg, statusCode=code, data=msg)
    return jsonify(isError= True,  message='Comething went wrong', statusCode=400)


@app.route('/api/login', methods=['POST'])
def login():
    content_type = request.headers.get('Content-Type')
    if 'application/json' in content_type:
        user_data = request.json['auth']
        code, msg = auth.auth(user_data)
        return jsonify(isError=(code!=200), message=msg, statusCode=code, data=msg)
    return jsonify(isError=True, statusCode=400, message="Something went wrong")

@app.route('/api/gettask', methods=['POST'])
def get_task():
    content_type = request.headers.get('Content-Type')
    if 'application/json' in content_type:
        try:
            user_data = request.json['auth']
            code, msg = auth.auth(user_data)
            if code!=200:
                logging.error('Authentification errors: %s',  user_data)
                return jsonify(isError=True, message=msg, statusCode=code)
            task_number = int(request.json['number'])
            case_number = auth.get_case_number(user_data['_id'], task_number)
            if case_number is None:
                case_number = task_list[task_number-1].generate_case_number()
                auth.set_case_number(user_data['_id'], task_number, case_number)
            case = task_list[task_number-1].get_case(case_number)
            return jsonify(isError=True, message='', statusCode=code, data=case.jsonify())
        except Exception as e: 
            logging.error('Failed to get task. Error code: %s', str(e))
            return jsonify(isError= True, message= 'Task not found', statusCode=404)

    return jsonify(isError= True, message= 'Something went wrong', statusCode=400)

@app.route('/api/send_task', methods=['POST'])
@limiter.limit("80/day")
def set_task():
    content_type = request.headers.get('Content-Type')
    if 'application/json' in content_type:
        user_data = request.json['auth']
        code, msg = auth.auth(user_data)
        if code!=200:
            return jsonify(isError=True, message=msg, statusCode=code)
        task_json= request.json['task']
        try:
            task_number = int(task_json['number'])
        except Exception as e: 
            logging.error('Failed to send task: %s', str(e))
            return jsonify(isError=True, message='Unknown task number', statusCode=400)
        
        count_attemps = auth.get_count_attemps(user_data['_id'], task_number)
        if count_attemps >= ATTEMPS_LIMIT:
            best_score = auth.get_best_score(user_data['_id'], task_number)
            return jsonify(isError=False, message= 'You\'ve run out of tries!(max={:d})\nYour max score:'.format(ATTEMPS_LIMIT), statusCode=200, data=best_score)

        case_number = auth.get_case_number(user_data['_id'], task_number)
        if case_number is None:
            return jsonify(isError= True, message= 'First you must get this task. You may have entered the wrong task number', statusCode=400)

        case = task_list[task_number-1].get_case(case_number)
        score = case.check(task_json['answers'])
        auth.set_task(user_data['_id'], case.jsonify(True), task_json, score.jsonify())
        return jsonify(isError= False, message='You have {:d} attempts left'.format(ATTEMPS_LIMIT-count_attemps-1), statusCode=code, data=score.jsonify())
        
    return jsonify(isError= True, message= 'Something went wrong', statusCode=400)


@app.route('/api/matlab_client_version', methods=['GET'])
def client_version():
    return jsonify(isError= False, message= 'Succes', statusCode=200, data=MATLAB_CLIENT_VERSION)

@app.route('/api/matlab_launcher_version', methods=['GET'])
def launcher_version():
    return jsonify(isError= False, message= 'Succes', statusCode=200, data=MATLAB_LAUNCHER_VERSION)

if __name__ == '__main__':
    # context = ('hdu2--cacert503.pem', 'localhost.pem')#certificate and key files
    # app.run(debug=True, ssl_context=context, host='127.0.0.1', port=port)
    app.run(debug=True, host=auth.host, port=auth.port)

    
