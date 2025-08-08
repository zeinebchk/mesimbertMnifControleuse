# services/session_manager.py
class SessionManager:
    _instance = None

    def __init__(self):
        self.access_token = None
        self.refresh_token = None
        self.username = None
        self.role=None
        self.modeleSelectionnee=None

    @classmethod
    def get_instance(cls):
        if cls._instance is None:
            cls._instance = SessionManager()
        return cls._instance
    def set_modele(self,modele):
        self.modeleSelectionnee = modele
    def set_tokens(self, access_token, refresh_token,username,role):
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.username = username
        self.role = role
    def get_modele(self):
        return self.modeleSelectionnee
    def get_access_token(self):
        return self.access_token

    def get_refresh_token(self):
        return self.refresh_token
    def get_username(self):
        return self.username
    def get_role(self):
        return self.role
