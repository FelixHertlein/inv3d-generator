import logging
import os
import subprocess
import sys
from multiprocessing import Process
from pathlib import Path
from time import sleep

import requests
from flask import Flask, request

from inv3d_generator.rendering.priority_lock import PriorityLock
from inv3d_generator.util import check_file

# prevent sever print messages
cli = sys.modules['flask.cli']
cli.show_server_banner = lambda *x: None

log = logging.getLogger('werkzeug')
log.disabled = True


class BlenderServer:
    PORT = 1234

    def __init__(self):
        self.p = Process(target=BlenderServer._run, args=(self.PORT,))
        self.p.start()
        self._wait_until_ready()

    def stop(self):
        self.p.terminate()

    @classmethod
    def execute_script(cls, code_file: Path, config_file: Path):
        check_file(code_file, suffix=".py")
        check_file(config_file, suffix=".json")

        requests.post(f'http://0.0.0.0:{cls.PORT}/execute', data={
            'code_file': str(code_file.expanduser().absolute()),
            'config_file': str(config_file.expanduser().absolute()),
            'priority': os.getpid()
        })

    @classmethod
    def _wait_until_ready(cls):
        while True:
            try:
                requests.get(f'http://0.0.0.0:{cls.PORT}/')
                return
            except requests.exceptions.ConnectionError:
                sleep(0.05)

    @staticmethod
    def _run(port: int):
        app = Flask(__name__)
        lock = PriorityLock()

        @app.route('/')
        def hello_world():
            return 'Hello, World!'

        @app.route('/execute', methods=['POST'])
        def execute():
            with lock(int(request.form["priority"])):
                code_file = request.form["code_file"]
                config_file = request.form["config_file"]
                command = f"blender --background -noaudio --python {code_file} -- {config_file}"
                process = subprocess.Popen(command, stdout=subprocess.DEVNULL, shell=True)
                process.wait()

                return "done"

        app.run(host='0.0.0.0', port=port)
