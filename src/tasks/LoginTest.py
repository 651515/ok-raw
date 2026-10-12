from math import fabs
import re

from qfluentwidgets import FluentIcon

from ok import FeatureSet, og
from src.tasks.MyBaseTask import MyBaseTask


class LoginTest(MyBaseTask):

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.name = "Login Test"
        self.description = "Test login function."
        self.icon = FluentIcon.SYNC
        self.default_config.update({
            "Wait Timeout": 5,
        })

        self.config_description.update({
            "Wait Timeout": "等待登录按钮可点击的超时时间（秒）",
        })

    def run(self):
        timeout = self.config.get("Wait Timeout",30)
        self.wait_click_feature(
            'start',
            time_out=timeout,
            raise_if_not_found=False,
            after_sleep=1,
        )
        self.log_info("Login Test Success")
    
        
