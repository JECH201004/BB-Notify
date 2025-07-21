```python
#!/usr/bin/env python3
import os
import pickle
import time
import requests
import argparse
from selenium import webdriver
from selenium.webdriver.common.by import By
from apscheduler.schedulers.blocking import BlockingScheduler
from sqlalchemy import create_engine, Column, String, Integer
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker
from dotenv import load_dotenv

# ————— Configuración —————
load_dotenv()
BB_USER   = os.getenv("BB_USER")        # Usuario SSO Blackboard
BB_PASS   = os.getenv("BB_PASS")        # Contraseña SSO Blackboard
WH_TOKEN  = os.getenv("WH_TOKEN")       # Token WhatsApp Cloud API
WH_PHONE  = os.getenv("WH_PHONE_ID")    # ID de tu número en WhatsApp
WH_DEST   = os.getenv("WH_DEST")        # Número destinatario de notificaciones (incluye país)
CHECK_INTERVAL = int(os.getenv("CHECK_INTERVAL_MIN", "120"))  # Intervalo en minutos

# ————— Base de datos local (SQLite) —————
engine = create_engine("sqlite:///blackboard.db")
Session = sessionmaker(bind=engine)
Base = declarative_base()

class Item(Base):
    __tablename__ = "items"
    id    = Column(Integer, primary_key=True)
    title = Column(String, nullable=False)
    link  = Column(String, unique=True, nullable=False)

Base.metadata.create_all(engine)

# ————— Funciones de Selenium —————
def get_driver():
    """
    Inicia un WebDriver de Chrome en modo headless. Asegúrate de tener chromedriver en el PATH.
    """
    opts = webdriver.ChromeOptions()
    opts.add_argument("--headless")
    return webdriver.Chrome(options=opts)


def login_blackboard(driver):
    """
    Automátiza el login SSO en Blackboard. Ajusta los selectores según tu institución.
    """
    driver.get("https://blackboard.mi-uni.edu.mx")
    time.sleep(2)
    # Reemplaza con los selectores exactos de los campos de usuario y contraseña
    driver.find_element(By.NAME, "user_id").send_keys(BB_USER)
    driver.find_element(By.NAME, "password").send_keys(BB_PASS)
    driver.find_element(By.CSS_SELECTOR, "button[type='submit']").click()
    time.sleep(5)
    # Guarda cookies para sesiones posteriores
    with open("cookies.pkl", "wb") as f:
        pickle.dump(driver.get_cookies(), f)


def load_cookies(driver):
    """
    Carga cookies de sesiones anteriores. Si no existen, realiza login y las guarda.
    """
    driver.get("https://blackboard.mi-uni.edu.mx")
    try:
        with open("cookies.pkl", "rb") as f:
            for cookie in pickle.load(f):
                driver.add_cookie(cookie)
    except FileNotFoundError:
        login_blackboard(driver)

# ————— Scraper de tareas y avisos —————
def fetch_new_items():
    """
    Extrae título y enlace de cada tarea/aviso nuevo en tu dashboard de Blackboard.
    """
    driver = get_driver()
    load_cookies(driver)
    driver.get("https://blackboard.mi-uni.edu.mx/ul/dashboard")
    time.sleep(3)
    items = []
    # Ajusta este selector al HTML real de tu Blackboard:
    elems = driver.find_elements(By.CSS_SELECTOR, ".item-selector")
    for elem in elems:
        title = elem.text.strip()
        # Obtiene el enlace ya sea del propio elemento o de un <a> interno
        link_element = elem.find_element(By.TAG_NAME, "a") if elem.get_attribute("href") is None else elem
        link = link_element.get_attribute("href")
        items.append((title, link))
    driver.quit()

    # Filtrado en base de datos
    session = Session()
    nuevos = []
    for title, link in items:
        if not session.query(Item).filter_by(link=link).first():
            nuevos.append((title, link))
            session.add(Item(title=title, link=link))
    session.commit()
    session.close()
    return nuevos

# ————— Envío de WhatsApp —————
def send_whatsapp(to, text):
    """
    Envía un mensaje de texto vía WhatsApp Cloud API.
    """
    url = f"https://graph.facebook.com/v17.0/{WH_PHONE}/messages"
    headers = {
        "Authorization": f"Bearer {WH_TOKEN}",
        "Content-Type": "application/json"
    }
    payload = {
        "messaging_product": "whatsapp",
        "to": to,
        "type": "text",
        "text": {"body": text}
    }
    resp = requests.post(url, json=payload, headers=headers)
    return resp.ok

# ————— Tarea programada —————
def job_check():
    """
    Función que se ejecuta periódicamente: extrae novedades y envía notificaciones.
    """
    nuevos = fetch_new_items()
    for title, link in nuevos:
        msg = f"📌 Nuevo en Blackboard:\n{title}\n{link}"
        send_whatsapp(WH_DEST, msg)


def start_scheduler():
    """
    Inicia un scheduler que corre job_check cada CHECK_INTERVAL minutos.
    """
    sched = BlockingScheduler()
    sched.add_job(job_check, 'interval', minutes=CHECK_INTERVAL)
    sched.start()

# ————— Punto de entrada —————
if __name__ == "__main__":
    parser = argparse.ArgumentParser()
    parser.add_argument("--once", action="store_true", help="Ejecutar chequeo una sola vez")
    args = parser.parse_args()

    if args.once:
        job_check()
    else:
        start_scheduler()
```
