import base64
import json
import os
from typing import *

from selenium import webdriver
from selenium.common.exceptions import TimeoutException
from selenium.webdriver.chrome.options import Options
from selenium.webdriver.support.expected_conditions import staleness_of
from selenium.webdriver.support.ui import WebDriverWait
from webdriver_manager.chrome import ChromeDriverManager

os.environ['WDM_LOG_LEVEL'] = '0'  # silence webdriver-manager


def convert(source: str, target: str, timeout: int = 2, print_options: Dict[str, Any] = None,
            install_driver: bool = True, script: Optional[str] = None):
    """
    Convert a given html file or website into PDF

    :param script:
    :param install_driver:
    :param print_options:
    :param str source: source html file or website link
    :param str target: target location to save the PDF
    :param int timeout: timeout in seconds. Default value is set to 2 seconds
   """

    if print_options is None:
        print_options = {}

    result = __get_pdf_from_html(source, timeout, install_driver, print_options=print_options, script=script)

    with open(target, 'wb') as file:
        file.write(result)


def __send_devtools(driver, cmd, params):
    resource = "/session/%s/chromium/send_command_and_get_result" % driver.session_id
    url = driver.command_executor._url + resource
    body = json.dumps({'cmd': cmd, 'params': params})
    response = driver.command_executor._request('POST', url, body)

    if not response:
        raise Exception(response.get('value'))

    return response.get('value')


def __get_pdf_from_html(path: str, timeout: int, install_driver: bool, print_options: Dict[str, str],
                        script: Optional[str] = None):
    webdriver_options = Options()
    webdriver_prefs = {}

    webdriver_options.add_argument('--headless')
    webdriver_options.add_argument('--disable-gpu')
    webdriver_options.add_argument('--no-sandbox')
    webdriver_options.add_argument('--disable-dev-shm-usage')
    webdriver_options.experimental_options['prefs'] = webdriver_prefs

    webdriver_prefs['profile.default_content_settings'] = {'images': 2}

    if install_driver:
        driver = webdriver.Chrome(ChromeDriverManager().install(), options=webdriver_options)
    else:
        driver = webdriver.Chrome(options=webdriver_options)

    driver.get(path)

    if script is not None:
        driver.execute_script(script)

    try:
        WebDriverWait(driver, timeout).until(staleness_of(driver.find_element_by_tag_name('html')))
    except TimeoutException:
        calculated_print_options = {
            'landscape': False,
            'displayHeaderFooter': False,
            'printBackground': True,
            'preferCSSPageSize': True,
        }
        calculated_print_options.update(print_options)
        result = __send_devtools(driver, "Page.printToPDF", calculated_print_options)
        driver.quit()
        return base64.b64decode(result['data'])
