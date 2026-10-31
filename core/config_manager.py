import json
import os

class ConfigManager:
    ENV_KEYS = {
        "c2_bind": ("CORUNA_C2_BIND", "C2_BIND"),
        "c2_port": ("CORUNA_C2_PORT", "C2_PORT"),
        "web_server_ip": ("CORUNA_WEB_SERVER_IP", "WEB_SERVER_IP", "WEB_IP"),
        "web_server_port": ("CORUNA_WEB_SERVER_PORT", "WEB_SERVER_PORT", "WEB_PORT", "PORT"),
        "exploit_templates_dir": ("CORUNA_EXPLOIT_TEMPLATES_DIR", "EXPLOIT_TEMPLATES_DIR"),
        "static_files_dir": ("CORUNA_STATIC_FILES_DIR", "STATIC_FILES_DIR"),
    }

    def __init__(self, config_path='config.json'):
        self.config_path = config_path
        self.config = self._load_config()

    def _load_config(self):
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except json.JSONDecodeError as e:
                raise ValueError(f"Invalid config in '{self.config_path}': {e}") from e
        else:
            default_config = {
                "c2_bind": "0.0.0.0",
                "c2_port": 8080,
                "web_server_ip": "0.0.0.0",
                "web_server_port": 80,
                "exploit_templates_dir": "exploits/",
                "static_files_dir": "web_server/static/",
            }
            try:
                print(f"[*] Creating default configuration file at '{self.config_path}'.")
                with open(self.config_path, "w", encoding="utf-8") as f:
                    json.dump(default_config, f, indent=4)
            except OSError:
                pass
            return default_config

    def get(self, key, default=None):
        env_vars = self.ENV_KEYS.get(key, (f"CORUNA_{key.upper()}", key.upper()))
        for env_var in env_vars:
            val = os.environ.get(env_var)
            if val is not None:
                cfg_val = self.config.get(key, default)
                if isinstance(cfg_val, int) or isinstance(default, int) or "port" in key:
                    try:
                        return int(val)
                    except ValueError:
                        return val
                return val
        return self.config.get(key, default)

    def set(self, key, value):
        self.config[key] = value

    def save_config(self):
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(self.config, f, indent=4)

if __name__ == "__main__":
    cm = ConfigManager()
    for k, v in cm.config.items():
        print(f"  {k}: {v}")
