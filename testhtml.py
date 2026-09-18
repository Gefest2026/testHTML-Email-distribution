import sys
import os
import pandas as pd
import logging
import re
import smtplib
import time
from PyQt5.QtCore import QThread
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from datetime import datetime
from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QHBoxLayout, QVBoxLayout,
    QSplitter, QTextEdit, QLabel, QPushButton, QFileDialog,
    QCheckBox, QLineEdit, QFormLayout, QGroupBox, QMessageBox,
    QTableWidget, QTableWidgetItem, QTabWidget, QProgressDialog
)
from PyQt5.QtWebEngineWidgets import QWebEngineView
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QColor, QPalette

# Настройка логирования
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(levelname)s - %(message)s',
    handlers=[
        logging.FileHandler('mailer.log'),
        logging.StreamHandler()
    ]
)

class MailerApp(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("HTML редактор и рассылка")
        self.setGeometry(100, 100, 1200, 800)
        self.logger = logging.getLogger(__name__)

        # Данные
        self.users_data = []

        # Таймер отложенного обновления превью
        self.update_timer = QTimer()
        self.update_timer.setSingleShot(True)
        self.update_timer.timeout.connect(self.update_preview)

        # UI
        self.init_ui()

        # Тема
        self.setup_dark_theme()

        # Стартовый HTML
        self.set_initial_html()

    def init_ui(self):
        central_widget = QWidget()
        self.setCentralWidget(central_widget)
        main_layout = QHBoxLayout(central_widget)

        splitter = QSplitter(Qt.Horizontal)

        # Левая панель с вкладками
        left_panel = QWidget()
        left_layout = QVBoxLayout(left_panel)
        self.tab_widget = QTabWidget()

        self.setup_html_tab()
        self.setup_mailing_tab()

        left_layout.addWidget(self.tab_widget)

        # Правая панель — только предпросмотр письма
        right_panel = QWidget()
        right_layout = QVBoxLayout(right_panel)
        self.preview = QWebEngineView()
        self.preview.setHtml("")
        right_layout.addWidget(QLabel("Предпросмотр письма:"))
        right_layout.addWidget(self.preview, stretch=1)

        splitter.addWidget(left_panel)
        splitter.addWidget(right_panel)
        splitter.setSizes([600, 600])
        main_layout.addWidget(splitter)

    def setup_html_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        self.editor = QTextEdit()
        self.editor.textChanged.connect(self.schedule_preview_update)

        btn_layout = QHBoxLayout()
        self.load_template_btn = QPushButton("Загрузить шаблон")
        self.load_template_btn.clicked.connect(self.load_html_template)
        self.save_template_btn = QPushButton("Сохранить шаблон")
        self.save_template_btn.clicked.connect(self.save_html_template)

        btn_layout.addWidget(self.load_template_btn)
        btn_layout.addWidget(self.save_template_btn)

        layout.addWidget(QLabel("HTML шаблон письма:"))
        layout.addWidget(self.editor)
        layout.addLayout(btn_layout)

        self.tab_widget.addTab(tab, "HTML редактор")

    def setup_mailing_tab(self):
        tab = QWidget()
        layout = QVBoxLayout(tab)

        # SMTP
        smtp_group = QGroupBox("Настройки SMTP")
        smtp_layout = QFormLayout()

        self.smtp_server = QLineEdit("smtp.yandex.ru")
        self.smtp_port = QLineEdit("465")
        self.smtp_user = QLineEdit()
        self.smtp_user.setPlaceholderText("Адрес почты")
        self.smtp_password = QLineEdit()
        self.smtp_password.setPlaceholderText("Пароль приложения")
        self.smtp_password.setEchoMode(QLineEdit.Password)
        self.email_subject = QLineEdit("Название рассылки")

        smtp_layout.addRow("SMTP сервер:", self.smtp_server)
        smtp_layout.addRow("Порт:", self.smtp_port)
        smtp_layout.addRow("Пользователь:", self.smtp_user)
        smtp_layout.addRow("Пароль:", self.smtp_password)
        smtp_layout.addRow("Тема письма:", self.email_subject)

        smtp_group.setLayout(smtp_layout)

        # Получатели
        self.recipients_table = QTableWidget()
        self.recipients_table.setColumnCount(4)
        self.recipients_table.setHorizontalHeaderLabels(["Выбрать", "Имя", "Фамилия", "Email"])
        self.recipients_table.horizontalHeader().setStretchLastSection(True)

        # Кнопки управления
        btn_layout = QHBoxLayout()
        self.load_recipients_btn = QPushButton("Загрузить получателей")
        self.load_recipients_btn.clicked.connect(self.load_recipients_via_dialog)
        self.select_all_btn = QPushButton("Выбрать всех")
        self.select_all_btn.clicked.connect(self.select_all_recipients)
        self.deselect_all_btn = QPushButton("Снять выбор")
        self.deselect_all_btn.clicked.connect(self.deselect_all_recipients)

        btn_layout.addWidget(self.load_recipients_btn)
        btn_layout.addWidget(self.select_all_btn)
        btn_layout.addWidget(self.deselect_all_btn)

        # Отправка
        self.send_btn = QPushButton("Отправить письма выбранным")
        self.send_btn.clicked.connect(self.send_emails)

        layout.addWidget(smtp_group)
        layout.addWidget(QLabel("Список получателей:"))
        layout.addWidget(self.recipients_table)
        layout.addLayout(btn_layout)
        layout.addWidget(self.send_btn)

        self.tab_widget.addTab(tab, "Рассылка")

    def setup_dark_theme(self):
        self.editor.setStyleSheet("""
            QTextEdit {
                background-color: #1e1e1e;
                color: #d4d4d4;
                font-family: Consolas, 'Courier New', monospace;
                font-size: 12pt;
                selection-background-color: #264f78;
                selection-color: #ffffff;
                border: 1px solid #3e3e3e;
            }
            QScrollBar:vertical {
                background: #1e1e1e;
                width: 12px;
                margin: 0px;
            }
            QScrollBar::handle:vertical {
                background: #424242;
                min-height: 20px;
            }
            QScrollBar::add-line:vertical, QScrollBar::sub-line:vertical {
                background: none;
            }
        """)

        app = QApplication.instance()
        app.setStyle("Fusion")
        dark_palette = QPalette()
        dark_palette.setColor(QPalette.Window, QColor(53, 53, 53))
        dark_palette.setColor(QPalette.WindowText, Qt.white)
        dark_palette.setColor(QPalette.Base, QColor(25, 25, 25))
        dark_palette.setColor(QPalette.AlternateBase, QColor(53, 53, 53))
        dark_palette.setColor(QPalette.ToolTipBase, Qt.white)
        dark_palette.setColor(QPalette.ToolTipText, Qt.white)
        dark_palette.setColor(QPalette.Text, Qt.white)
        dark_palette.setColor(QPalette.Button, QColor(53, 53, 53))
        dark_palette.setColor(QPalette.ButtonText, Qt.white)
        dark_palette.setColor(QPalette.BrightText, Qt.red)
        dark_palette.setColor(QPalette.Link, QColor(42, 130, 218))
        dark_palette.setColor(QPalette.Highlight, QColor(42, 130, 218))
        dark_palette.setColor(QPalette.HighlightedText, Qt.black)
        app.setPalette(dark_palette)

    def set_initial_html(self):
        initial_html = """"""
        self.editor.setPlainText(initial_html)
        self.update_preview()

    def schedule_preview_update(self):
        self.update_timer.start(400)

    def update_preview(self):
        html_content = self.editor.toPlainText()
        self.preview.setHtml(html_content)

    def load_html_template(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Загрузить HTML шаблон", "", "HTML Files (*.html *.htm);;All Files (*)")
        if file_path:
            try:
                with open(file_path, 'r', encoding='utf-8') as f:
                    self.editor.setPlainText(f.read())
                self.logger.info("HTML шаблон загружен")
            except Exception as e:
                self.logger.error("Ошибка загрузки HTML шаблона")
                QMessageBox.warning(self, "Ошибка", f"Не удалось загрузить файл: {str(e)}")

    def save_html_template(self):
        file_path, _ = QFileDialog.getSaveFileName(self, "Сохранить HTML шаблон", "", "HTML Files (*.html *.htm);;All Files (*)")
        if file_path:
            try:
                with open(file_path, 'w', encoding='utf-8') as f:
                    f.write(self.editor.toPlainText())
                self.logger.info("HTML шаблон сохранен")
                QMessageBox.information(self, "Успех", "Шаблон успешно сохранен")
            except Exception as e:
                self.logger.error("Ошибка сохранения HTML шаблона")
                QMessageBox.warning(self, "Ошибка", f"Не удалось сохранить файл: {str(e)}")

    def load_recipients_via_dialog(self):
        file_path, _ = QFileDialog.getOpenFileName(self, "Загрузить получателей", "", "Excel Files (*.xlsx *.xls);;CSV Files (*.csv);;All Files (*)")
        if not file_path:
            return
        try:
            if file_path.endswith('.csv'):
                df = pd.read_csv(file_path)
            elif file_path.endswith(('.xlsx', '.xls')):
                df = pd.read_excel(file_path)
            else:
                raise ValueError("Неподдерживаемый формат файла")

            required_columns = ["name", "surname", "email"]
            if not all(col in df.columns for col in required_columns):
                raise ValueError(f"Файл должен содержать колонки: {required_columns}")

            df['name'] = df['name'].astype(str).str.strip()
            df['surname'] = df['surname'].astype(str).str.strip()
            df['email'] = df['email'].astype(str).str.strip()

            self.users_data = df.to_dict('records')
            self.update_recipients_table()
            self.logger.info("Загружены получатели, всего: %d", len(self.users_data))
        except Exception as e:
            self.logger.error("Ошибка загрузки получателей")
            QMessageBox.warning(self, "Ошибка", f"Не удалось загрузить данные: {str(e)}")

    def update_recipients_table(self):
        self.recipients_table.setRowCount(len(self.users_data))
        for i, user in enumerate(self.users_data):
            checkbox = QCheckBox()
            checkbox.setChecked(True)
            checkbox_widget = QWidget()
            layout = QHBoxLayout(checkbox_widget)
            layout.addWidget(checkbox)
            layout.setAlignment(Qt.AlignCenter)
            layout.setContentsMargins(0, 0, 0, 0)
            self.recipients_table.setCellWidget(i, 0, checkbox_widget)

            self.recipients_table.setItem(i, 1, QTableWidgetItem(user.get('name', '')))
            self.recipients_table.setItem(i, 2, QTableWidgetItem(user.get('surname', '')))
            self.recipients_table.setItem(i, 3, QTableWidgetItem(user.get('email', '')))

    def select_all_recipients(self):
        for i in range(self.recipients_table.rowCount()):
            checkbox = self.recipients_table.cellWidget(i, 0).findChild(QCheckBox)
            if checkbox:
                checkbox.setChecked(True)
        self.logger.info("Выбраны все получатели")

    def deselect_all_recipients(self):
        for i in range(self.recipients_table.rowCount()):
            checkbox = self.recipients_table.cellWidget(i, 0).findChild(QCheckBox)
            if checkbox:
                checkbox.setChecked(False)
        self.logger.info("Снят выбор со всех получателей")

    def get_selected_recipients(self):
        selected = []
        for i in range(self.recipients_table.rowCount()):
            checkbox = self.recipients_table.cellWidget(i, 0).findChild(QCheckBox)
            if checkbox and checkbox.isChecked():
                selected.append(self.users_data[i])
        return selected

    def send_emails(self):
        if not all([self.smtp_server.text(), self.smtp_port.text(), self.smtp_user.text(), self.smtp_password.text()]):
            self.logger.warning("Не заполнены настройки SMTP")
            QMessageBox.warning(self, "Ошибка", "Заполните все настройки SMTP")
            return

        # Проверка подключения к SMTP серверу
        try:
            with smtplib.SMTP_SSL(self.smtp_server.text(), int(self.smtp_port.text()), timeout=10) as test_server:
                test_server.login(self.smtp_user.text(), self.smtp_password.text())
        except Exception as e:
            QMessageBox.warning(self, "Ошибка SMTP", f"Не удалось подключиться к SMTP серверу: {str(e)}")
            return

        recipients = self.get_selected_recipients()
        if not recipients:
            self.logger.warning("Не выбраны получатели для отправки")
            QMessageBox.warning(self, "Ошибка", "Не выбраны получатели")
            return

        confirm = QMessageBox.question(
            self,
            "Подтверждение",
            f"Отправить письма {len(recipients)} получателям?",
            QMessageBox.Yes | QMessageBox.No
        )
        if confirm != QMessageBox.Yes:
            self.logger.info("Отправка писем отменена пользователем")
            return

        success_mail = 0
        fail_mail = 0
        progress = QProgressDialog("Отправка писем...", "Отмена", 0, len(recipients), self)
        progress.setWindowTitle("Отправка")
        progress.setWindowModality(Qt.WindowModal)

        # Получаем шаблон один раз перед циклом
        template = self.editor.toPlainText().strip()

        for i, user in enumerate(recipients):
            progress.setValue(i)
            if progress.wasCanceled():
                self.logger.info("Отправка писем прервана пользователем")
                break

            email = user.get('email', '')
            
            # Валидация email
            if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
                self.logger.error("Неверный формат email у получателя №%d", i + 1)
                fail_mail += 1
                continue

            try:
                # Создаем копию шаблона для каждого пользователя
                email_body = template
                
                # Заменяем переменные безопасным способом
                replacements = {
                   "{name}": str(user.get("name", "")),
                   "{surname}": str(user.get("surname", "")),
                   "{card_number}": str(user.get("card_number", "")),
                   "{year}": str(datetime.now().year)
                 }
                
                for placeholder, value in replacements.items():
                    email_body = email_body.replace(placeholder, value)

                # Проверка HTML тегов
                if "<html>" not in email_body.lower() or "<body>" not in email_body.lower():
                    self.logger.error("Тело письма не содержит HTML тегов для получателя №%d", i + 1)
                    fail_mail += 1
                    continue

                # Создание сообщения
                msg = MIMEMultipart()
                msg["From"] = self.smtp_user.text()
                msg["To"] = email
                msg["Subject"] = self.email_subject.text()
                msg.attach(MIMEText(email_body, "html", "utf-8"))

                # Отправка с обработкой ошибок лимитов
                with smtplib.SMTP_SSL(self.smtp_server.text(), int(self.smtp_port.text()), timeout=10) as server:
                    server.login(self.smtp_user.text(), self.smtp_password.text())
                    server.send_message(msg)
                
                success_mail += 1
                self.logger.info("Письмо успешно отправлено получателю №%d", i + 1)
                
                # Задержка между отправками (1 секунда) - исправленная строка
                QApplication.processEvents()
                QThread.sleep(1)  # Используем QThread.sleep вместо time.sleep
                
            except smtplib.SMTPDataError as e:
                if "message rate limit" in str(e):
                    self.logger.warning("Превышен лимит отправки для получателя №%d. Письмо будет пропущено.", i + 1)
                    fail_mail += 1
                    QMessageBox.warning(self, "Лимит отправки", 
                                       f"Почтовый сервер получателя {email} временно отклоняет письма.\n\n"
                                       f"Ошибка: {str(e)}\n\n"
                                       f"Попробуйте отправить этому получателю позже.")
                    continue
                else:
                    raise
                    
            except Exception as e:
                fail_mail += 1
                error_msg = f"Ошибка отправки письма получателю №{i + 1}"
                self.logger.error(error_msg)
                print(error_msg)

        progress.close()

        report_msg = f"Писем успешно отправлено: {success_mail}, не удалось отправить: {fail_mail}"
        self.logger.info(report_msg)
        QMessageBox.information(
            self,
            "Отчет",
            report_msg
        )

if __name__ == "__main__":
    app = QApplication(sys.argv)
    window = MailerApp()
    window.show()
    sys.exit(app.exec_())