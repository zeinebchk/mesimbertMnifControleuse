import socketio
from kivy.app import App
from kivy.lang import Builder
from kivy.uix.screenmanager import ScreenManager
from kivy.core.window import Window

from kivymd.app import MDApp

from SessionManager import SessionManager
from login import LoginScreen
from scan import BarCodeScennerScreen
# Taille pour test
Window.size = (900, 600)

sio = socketio.Client()
class MainApp(MDApp):
    def build(self):
        self.theme_cls.primary_palette = "Blue"
        self.theme_cls.theme_style = "Light"
        sio.connect("http://127.0.0.1:5001")

        # Chargement des fichiers .kv
        Builder.load_file("loginscreen.kv")
        Builder.load_file("scan.kv")

        # Chargement du screenmanager défini dans maintv.kv
        return Builder.load_file("main.kv")
    def on_logout(self):
        session = SessionManager().get_instance()
        session.set_tokens(None, None, None, None)

        print(session.get_access_token())
        print(session.get_refresh_token())

        # Obtenir le ScreenManager principal
        screen_manager = App.get_running_app().root

        # Ajouter login_screen s’il n’existe pas déjà
        if not screen_manager.has_screen("login_screen"):
            screen = LoginScreen(name="login_screen")
            screen_manager.add_widget(screen)

        # Rediriger vers login_screen
        screen_manager.current = "login_screen"
if __name__ == "__main__":
    MainApp().run()