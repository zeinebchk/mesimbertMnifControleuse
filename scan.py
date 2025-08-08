import sys
import logging
import re
from kivy.app import App
from kivy.properties import StringProperty, BooleanProperty
from kivy.uix.boxlayout import BoxLayout
from kivy.uix.label import Label
from kivy.uix.screenmanager import Screen
from kivy.uix.textinput import TextInput
from kivy.uix.button import Button
from kivy.uix.popup import Popup
from kivy.uix.gridlayout import GridLayout
from kivy.core.window import Window
from kivy.metrics import dp
from kivy.graphics import Color, RoundedRectangle
import pymysql
from datetime import datetime

from SessionManager import SessionManager
from client import make_request

# Configure file-based logging
logging.basicConfig(level=logging.DEBUG, filename='barcode_scanner.log', filemode='w',
                    format='%(asctime)s - %(levelname)s - %(message)s')


class BarCodeScennerScreen(Screen):
    user_info_text = StringProperty("Utilisateur: -")
    info_text = StringProperty("Scanner un code-barres pour voir les informations")
    show_accept_similar = BooleanProperty(False)
    def __init__(self, db_config=None,**kwargs):
        super().__init__(**kwargs)

        self.current_user=None
        self.login_screen = None
        self.main_screen = None
        self.current_paire_par_scan = 0
        self.accept_similar_mode = False
        self.base_of_for_similar = None
        self.db_config = db_config or {
            'host': '127.0.0.1',
            'user': 'root',
            'password': '',
            'database': 'mesimbertmnif',
            'charset': 'utf8mb4',
            'connect_timeout': 5
        }
        self.conn = pymysql.connect(**self.db_config)
        self.cursor = self.conn.cursor(pymysql.cursors.DictCursor)
        print(self.cursor)
        self.initialise_user()

    def initialise_user(self):
        session = SessionManager.get_instance()
        print(session.get_username())
        print(session.get_role())
        self.current_user = {"username": session.get_username(), "role": session.get_role()}
        print(self.current_user)
    def clear_input(self, instance):
        logging.debug("Clearing barcode input")
        self.ids.barcode_entry.text = ""
        self.ids.barcode_entry.focus = True
        if hasattr(self, 'base_of_for_similar'):
            del self.base_of_for_similar
        self.accept_similar_mode = False

    def show_popup(self, title, message):
        popup = Popup(title=title, content=Label(text=message, font_size=dp(16), color=(1, 1, 1, 1)),
                      size_hint=(0.8, 0.4), background_color=(0.0, 0.4, 0.4, 1),
                      title_color=(1, 1, 1, 1), title_size=dp(18))
        popup.open()

    def show_paire_par_scan_dialog(self, num_of, pointure):
        content = BoxLayout(orientation='vertical', spacing=dp(10), padding=dp(15))

        current_value = Label(text=f"Valeur actuelle: {self.current_paire_par_scan}")
        input_field = TextInput(text=str(self.current_paire_par_scan), input_filter='int')

        def save_changes(instance):
            try:
                new_value = int(input_field.text)
                if new_value > 0:
                    self.update_paire_par_scan(num_of, pointure, new_value)
                    popup.dismiss()
                else:
                    self.show_popup("Erreur", "La valeur doit être supérieure à 0")
            except ValueError:
                self.show_popup("Erreur", "Veuillez entrer un nombre valide")

        btn_layout = BoxLayout(spacing=dp(10))
        btn_layout.add_widget(Button(text="Annuler", on_press=lambda x: popup.dismiss()))
        btn_layout.add_widget(Button(text="Valider", on_press=save_changes))

        content.add_widget(current_value)
        content.add_widget(Label(text="Nouvelle valeur:"))
        content.add_widget(input_field)
        content.add_widget(btn_layout)

        popup = Popup(title="Modifier paires/scan", content=content, size_hint=(0.8, 0.4))
        popup.open()

    def update_paire_par_scan(self, num_of, pointure, new_value):
        try:


            self.cursor.execute("""
                           UPDATE barcode_scans
                           SET paire_par_scan  = %s,
                               remaining_pairs = (SELECT Quantite FROM ofs WHERE numOF = %s) - (current_scans * %s)
                           WHERE of_number = %s
                             AND size = %s
                             AND username = %s
                           """, (new_value, num_of, new_value, num_of, pointure, self.current_user['username']))
            self.conn.commit()
            self.current_paire_par_scan = new_value
            logging.info(f"Updated paire_par_scan to {new_value} for OF={num_of}, Pointure={pointure}, User={self.current_user['username']}")
            self.show_popup("Succès", f"Paires par scan mises à jour à {new_value}")
        except pymysql.Error as e:
            logging.error(f"Error updating paire_par_scan: {str(e)}")
            self.show_popup("Erreur", f"Échec de la mise à jour: {str(e)}")
        finally:
            if self.cursor:
                self.cursor.close()
            if self.conn:
                self.conn.close()

    def activate_accept_similar_mode(self):
        self.accept_similar_mode = True
        self.show_popup("Mode Activation",
                        "Mode 'Accepter OF similaire' activé. Scannez d'abord l'OF de base, puis l'OF cible.")
        self.clear_input(None)

    def accept_similar_ofs(self, base_of, target_of):

        try:


            # Vérifier que les OF existent et ont la même forme
            self.cursor.execute("""
                           SELECT numOF, Modele, Coloris, Pointure, Quantite
                           FROM ofs
                           WHERE numOF IN (%s, %s)
                           """, (base_of, target_of))

            ofs_data = self.cursor.fetchall()
            if len(ofs_data) != 2:
                self.show_popup("Erreur", "Un des OF n'a pas été trouvé")
                return False

            base_data = next((item for item in ofs_data if item['numOF'] == base_of), None)
            target_data = next((item for item in ofs_data if item['numOF'] == target_of), None)

            if not base_data or not target_data:
                self.show_popup("Erreur", "Erreur de récupération des données OF")
                return False

            if (base_data['Modele'] != target_data['Modele'] or
                    base_data['Coloris'] != target_data['Coloris'] or
                    base_data['Pointure'] != target_data['Pointure']):
                self.show_popup("Erreur", "Les OF n'ont pas les mêmes caractéristiques (Modèle/Coloris/Pointure)")
                return False

            # Vérifier si l'OF de base a une configuration de scan pour cet utilisateur
            self.cursor.execute("""
                           SELECT *
                           FROM barcode_scans
                           WHERE of_number = %s
                             AND username = %s
                           """, (base_of, self.current_user['username']))
            base_scan_config = self.cursor.fetchone()

            if not base_scan_config:
                self.show_popup("Erreur", f"L'OF de base {base_of} n'a pas de configuration de scan pour cet utilisateur")
                return False

            # Copier la configuration de l'OF de base vers l'OF cible pour cet utilisateur
            self.cursor.execute("""
                           INSERT INTO barcode_scans (of_number, size, max_scans, current_scans, paire_par_scan,
                                                      remaining_pairs, last_scan, last_phase, username)
                           VALUES (%s, %s, %s, 0, %s, %s, NULL, NULL, %s)
                           """, (
                               target_of,
                               base_data['Pointure'],
                               base_scan_config['max_scans'],
                               base_scan_config['paire_par_scan'],
                               target_data['Quantite'],  # remaining_pairs initial = Quantité totale
                               self.current_user['username']
                           ))

            self.conn.commit()
            self.show_popup("Succès", f"L'OF {target_of} a été configuré comme {base_of} pour {self.current_user['username']}")
            return True

        except pymysql.Error as e:
            logging.error(f"Error accepting similar OFs: {str(e)}")
            self.show_popup("Erreur DB", f"Échec de l'opération: {str(e)}")
            return False
        finally:
            if self.cursor:
                self.cursor.close()
            if self.conn:
                self.conn.close()

    def process_barcode(self):
        if not self.current_user:
            self.show_popup("Erreur", "Session expirée. Veuillez vous reconnecter.")
            logging.error("No current user, session expired")
            return

        barcode = self.ids.barcode_entry.text.strip()
        logging.debug(f"Processing barcode: {barcode} by user {self.current_user['username']}")

        if not barcode:
            logging.warning("No barcode input provided")
            self.show_popup("Erreur", "Veuillez scanner un code-barres")
            self.clear_input(None)
            return

        # Mode accept similar OF
        if self.accept_similar_mode:
            if not hasattr(self, 'base_of_for_similar'):
                self.base_of_for_similar = barcode
                self.show_popup("Info", f"OF de base {barcode} enregistré. Scannez maintenant l'OF cible.")
                self.clear_input(None)
                return
            else:
                target_of = barcode
                success = self.accept_similar_ofs(self.base_of_for_similar, target_of)
                if hasattr(self, 'base_of_for_similar'):
                    del self.base_of_for_similar
                self.accept_similar_mode = False
                self.clear_input(None)
                return

        try:
            # Nettoyage du code-barres
            cleaned_barcode = barcode.replace(')', '-').replace('!', '-').replace(' ', '')
            cleaned_barcode = '-'.join(filter(None, cleaned_barcode.split('-')))

            logging.info(f"Cleaned barcode: {barcode} -> {cleaned_barcode}")

            # Découpage des parties
            parts = cleaned_barcode.split('-')

            # Validation du format
            if len(parts) < 3:
                raise ValueError("Format de code-barres invalide")

            num_of = parts[0]
            pointure = parts[1]
            print("pointure", pointure)
            # Gestion des pointures composées et conversion en entier
            try:
                if len(parts) > 3 and parts[2].isdigit() and '/' not in pointure:
                    pointure += '/' + parts[2]
                    scans_autorises = int(parts[3]) if len(parts) > 3 else 1
                else:
                    scans_autorises = int(parts[2]) if len(parts) > 2 else 1
            except (ValueError, IndexError):
                scans_autorises = 1  # Valeur par défaut si conversion échoue

            # Validation du numéro OF
            if not num_of.isdigit():
                raise ValueError(f"Numéro OF invalide: {num_of}")
            # Connexion à la base de données


            # Vérification de l'OF
            self.cursor.execute("""
                           SELECT numOF, Pointure, Quantite, Modele, Coloris
                           FROM ofs
                           WHERE numOF = %s
                           """, (num_of,))
            of_data = self.cursor.fetchone()

            if not of_data:
                logging.error(f"No OF found for number: {num_of}")
                self.show_popup("Erreur", f"Aucun OF trouvé avec le numéro {num_of}")
                self.clear_input(None)
                return

            # Normalisation des pointures pour comparaison
            db_pointure = of_data['Pointure'].replace(' ', '').lower()
            scanned_pointure = pointure.replace(' ', '').lower()
            print("pointure base",db_pointure)
            print("scanned pointure",scanned_pointure)
            # Comparaison flexible des pointures
            if db_pointure != scanned_pointure:
                # Vérification si c'est une sous-pointure (ex: 35 dans 35/36)
                if '/' in db_pointure and scanned_pointure in db_pointure.split('/'):
                    logging.info(f"Sub-size match: scanned {scanned_pointure} is part of {db_pointure}")
                else:
                    logging.warning(
                        f"Pointure mismatch: scanned {scanned_pointure}, expected {db_pointure} for OF {num_of}")
                    self.show_popup("Erreur",
                                    f"Pointure scannée ({pointure}) ne correspond pas à celle de l'OF ({of_data['Pointure']})")
                    self.clear_input(None)
                    return

            # Calculate paire_par_scan
            try:
                quantite = int(of_data['Quantite']) if of_data['Quantite'] is not None else 0
                if quantite <= 0:
                    raise ValueError(f"Quantité invalide: {of_data['Quantite']}")

                # Vérification que scans_autorises est bien un nombre
                if not isinstance(scans_autorises, int):
                    scans_autorises = 1  # Valeur par défaut
                    logging.warning(f"Scans_autorises n'est pas un entier, utilisation de la valeur par défaut 1")

                paire_par_scan = quantite // scans_autorises
                if paire_par_scan <= 0:
                    paire_par_scan = 1
                    logging.warning("Calculated paire_par_scan <= 0, setting to 1")

                logging.debug(f"Calculated paire_par_scan={paire_par_scan}")

            except ValueError as ve:
                logging.error(f"Error calculating paire_par_scan: {str(ve)}")
                self.show_popup("Erreur", f"Erreur de calcul: {str(ve)}")
                self.clear_input(None)
                return

            # Fetch or initialize barcode scan data for this user
            self.cursor.execute("""
                           SELECT of_number, size, max_scans, current_scans, paire_par_scan, remaining_pairs, last_scan, username
                           FROM barcode_scans
                           WHERE of_number = %s
                             AND size = %s
                             AND username = %s
                           """, (num_of, pointure, self.current_user['role']))
            scan_data = self.cursor.fetchone()

            if not scan_data:
                logging.info(f"No scan data for OF: {num_of}, Pointure: {pointure}, User: {self.current_user['role']}. Initializing.")
                default_remaining_pairs = quantite
                self.cursor.execute("""
                               INSERT INTO barcode_scans (of_number, size, max_scans, current_scans, paire_par_scan,
                                                          remaining_pairs, username)
                               VALUES (%s, %s, %s, %s, %s, %s, %s)
                               """, (num_of, pointure, scans_autorises, 0, paire_par_scan, default_remaining_pairs, self.current_user['role']))
                self.conn.commit()
                # Verify inserted data
                self.cursor.execute("""
                               SELECT of_number, size, max_scans, current_scans, paire_par_scan, remaining_pairs, username
                               FROM barcode_scans
                               WHERE of_number = %s
                                 AND size = %s
                                 AND username = %s
                               """, (num_of, pointure, self.current_user['role']))
                scan_data = self.cursor.fetchone()
                if not scan_data or scan_data['paire_par_scan'] != paire_par_scan:
                    logging.error(
                        f"Initialization failed: expected paire_par_scan={paire_par_scan}, got {scan_data['paire_par_scan'] if scan_data else 'None'}")
                    self.show_popup("Erreur DB", "Échec de l'initialisation de paire_par_scan")
                    self.clear_input(None)
                    return
            else:
                # Update paire_par_scan if incorrect
                if scan_data['paire_par_scan'] != paire_par_scan:
                    logging.warning(
                        f"Existing paire_par_scan={scan_data['paire_par_scan']} does not match calculated={paire_par_scan}. Updating.")
                    self.cursor.execute("""
                                   UPDATE barcode_scans
                                   SET paire_par_scan = %s
                                   WHERE of_number = %s
                                     AND size = %s
                                     AND username = %s
                                   """, (paire_par_scan, num_of, pointure, self.current_user['role']))
                    self.conn.commit()
                    # Re-fetch to confirm
                    self.cursor.execute("""
                                   SELECT of_number, size, max_scans, current_scans, paire_par_scan, remaining_pairs, username
                                   FROM barcode_scans
                                   WHERE of_number = %s
                                     AND size = %s
                                     AND username = %s
                                   """, (num_of, pointure, self.current_user['role']))
                    scan_data = self.cursor.fetchone()
                    if scan_data['paire_par_scan'] != paire_par_scan:
                        logging.error(
                            f"Update failed: expected paire_par_scan={paire_par_scan}, got {scan_data['paire_par_scan']}")
                        self.show_popup("Erreur DB", "Échec de la mise à jour de paire_par_scan")
                        self.clear_input(None)
                        return

            # Set current_paire_par_scan
            self.current_paire_par_scan = scan_data['paire_par_scan']
            logging.debug(f"Set self.current_paire_par_scan={self.current_paire_par_scan}")

            # Validate scan count
            if scan_data['current_scans'] > scan_data['max_scans']:
                logging.warning(f"Maximum scans reached for OF: {num_of} by user: {self.current_user['role']}")
                self.show_popup("Limite Atteinte", f"Nombre maximum de scans atteint pour OF {num_of}")
                self.clear_input(None)

                return

            # Update scan data
            new_current_scans = scan_data['current_scans'] + 1
            new_remaining_pairs = max(0, scan_data['remaining_pairs'] - scan_data['paire_par_scan'])
            current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
            phase = self.current_user['role']
            if new_current_scans == 1:
                print("11111111111")
                data = [{
                    "numOF": num_of,
                    "chaine": self.current_user["role"]
                }]
                response = make_request("put", "/manage_ofs/launch_of", json=data)
                if response.json()[1] == 201:
                    print("success")
            if new_current_scans == scan_data['max_scans']:
                print("================")
                data = {
                    "numOF": num_of,
                    "chaine": self.current_user["role"]
                }
                response = make_request("put", "/manage_ofs/update_to_done", json=data)
                if response.json()[1] == 201:
                    print("success")
            self.cursor.execute("""
                           UPDATE barcode_scans
                           SET current_scans   = %s,
                               remaining_pairs = %s,
                               last_scan       = %s,
                               last_phase      = %s
                           WHERE of_number = %s
                             AND size = %s
                             AND username = %s
                           """, (new_current_scans, new_remaining_pairs, current_time, phase, num_of, pointure, self.current_user['role']))

            # Log scan in history
            self.cursor.execute("""
                           INSERT INTO scan_history (of_number, size, scan_time, phase, username, original_barcode,
                                                     cleaned_barcode, max_scans, current_scans, paire_par_scan,
                                                     remaining_pairs, model, color, quantity)
                           VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                           """, (num_of, pointure, current_time, phase, self.current_user['role'], barcode,
                                 cleaned_barcode, scan_data['max_scans'], new_current_scans,
                                 scan_data['paire_par_scan'],
                                 new_remaining_pairs, of_data['Modele'], of_data['Coloris'], of_data['Quantite']))
            self.conn.commit()

            # Display information
            progress_percentage = (new_current_scans / scan_data['max_scans'] * 100) if scan_data[
                                                                                            'max_scans'] > 0 else 0
            label_color = "000000"  # noir
            info_text = (
                f"[b][color={label_color}]OF:[/color][/b] {of_data['numOF']}\n"
                f"[b][color={label_color}]Pointure:[/color][/b] {of_data['Pointure']}\n"
                f"[b][color={label_color}]Quantité:[/color][/b] {of_data['Quantite']}\n"
                f"[b][color={label_color}]Modèle:[/color][/b] {of_data['Modele']}\n"
                f"[b][color={label_color}]Coloris:[/color][/b] {of_data['Coloris']}\n"
                f"[b][color={label_color}]Scans effectués:[/color][/b] {new_current_scans}/{scan_data['max_scans']}\n"
                f"[b][color={label_color}]Progrès:[/color][/b] {progress_percentage:.2f}%\n"
                f"[b][color={label_color}]Paires par scan:[/color][/b] {scan_data['paire_par_scan']}\n"
                f"[b][color={label_color}]Paires restantes:[/color][/b] {new_remaining_pairs}\n"
                f"[b][color={label_color}]Phase:[/color][/b] {phase}\n"
                f"[b][color={label_color}]Dernier scan:[/color][/b] {current_time}"
            )

            self.ids.info_display.text = info_text
            logging.info(
                f"Scan successful: OF={num_of}, Pointure={pointure}, Pairs per scan={scan_data['paire_par_scan']}, User={self.current_user['role']}")
            data={
                "date": datetime.now().strftime("%Y/%m/%d"),
                "numOf" :num_of,
                "nbPaire" : scan_data['paire_par_scan'],
                "modele" :of_data['Modele']
            }
            response = make_request("post", "/manage_production/save_production", json=data)
            if response.json()[1] == 200:
                print("sucees de production")
            # Add modify button for supervisors
        except ValueError as ve:
            logging.error(f"Invalid barcode format: {str(ve)}")
            self.show_popup("Erreur", f"Erreur de format de code-barres: {str(ve)}")
            self.clear_input(None)
        except pymysql.Error as e:
            logging.error(f"Database error: {str(e)}")
            self.show_popup("Erreur DB", f"Erreur base de données: {str(e)}")
            print(str(e))
            self.clear_input(None)
        except Exception as e:
            logging.error(f"Unexpected error: {str(e)}")
            self.show_popup("Erreur", f"Erreur inattendue: {str(e)}")
            self.clear_input(None)


