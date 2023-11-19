import firebase_admin                   #--\
from firebase_admin import credentials  #--->파이어베이스 관련 라이브러리
from firebase_admin import firestore    #--/
import time
import spidev                           #spi 통신(토양수분센서)
import Adafruit_DHT                     #온습도센서
import RPi.GPIO as GPIO                 #GPIO
from multiprocessing import Process     #멀티프로세싱
import subprocess                       #쉘 명령을 실행하기 위한 라이브러리
import smbus                            # i2c 라이브러리

GPIO.setmode(GPIO.BCM)
sensor = Adafruit_DHT.DHT22
pin = 4
GPIO.setwarnings(False)
GPIO.setup(19, GPIO.OUT, initial=1)
GPIO.setup(20, GPIO.OUT, initial=1)
GPIO.setup(21, GPIO.OUT, initial=1)
GPIO.setup(26, GPIO.OUT, initial=1)
GPIO.setup(16, GPIO.OUT, initial=1)
GPIO.setup(13, GPIO.OUT, initial=GPIO.HIGH)
GPIO.setup(6, GPIO.OUT, initial=GPIO.HIGH)


spi=spidev.SpiDev()
spi.open(0,0)
spi.max_speed_hz=50000

#Firebase에 연결하여 db라는 공간을 생성
cred = credentials.Certificate('/home/jkhRpi/Downloads/nsuplantmonitoring-firebase-adminsdk-ac6ax-0d04a6c108.json')
default_app = firebase_admin.initialize_app(cred)
db = firestore.client()

#연결된 db라는 공간에 해당하는 값을 내려받음
doc_ref = db.collection(u'sensor').document(u'data')
doc_temp = doc_ref.get()


if doc_temp.get('temp') is None:
     co2 = int(doc_temp.get('co2'))
     soil_water = int(doc_temp.get('soil'))
     lux = int(doc_temp.get('lux'))

else :
     temperature = int(doc_temp.get('temp'))
     co2 = int(doc_temp.get('co2'))
     humidity = int(doc_temp.get('humidity'))
     soil_water = int(doc_temp.get('soil'))
     lux = int(doc_temp.get('lux'))


def read_spi_adc(adcChannel):       ##spi 통신으로 mcp3008에서 데이터를 읽어오는 함수
    adcValue=0
    buff=spi.xfer2([1,(8+adcChannel)<<4,0])                                                                                                       
    adcValue = ((buff[1]&3)<<8)+buff[2]
    return adcValue

def func_temp_control():    ##온도조절 (냉온풍 및 펠티어)
    while True:
        global doc_temp
        doc_temp = doc_ref.get()
        temperature = int(doc_temp.get('temp'))
        temperature_dest_low = int(doc_temp.get('temp_dest_low'))
        temperature_dest_high = int(doc_temp.get('temp_dest_high'))
        if temperature < temperature_dest_low :
            GPIO.output(26,False)        ##릴레이 펠티어 on
            GPIO.output(20,False)        ##릴레이 온풍팬 on      
            GPIO.output(21,True)       ##릴레이 냉풍팬 off  
        elif temperature > temperature_dest_high :
            GPIO.output(26,False)        ##릴레이 펠티어 on
            GPIO.output(21,False)        ##릴레이 냉풍팬 on
            GPIO.output(20,True)       ##릴레이 온풍팬 off
        else :
            GPIO.output(26,True)       ##릴레이 펠티어 off
            GPIO.output(21,True)       ##릴레이 냉풍팬 off
            GPIO.output(20,True)       ##릴레이 온풍팬 off
        time.sleep(5)

def func_ventilation():
     while True:
          global doc_temp
          doc_temp = doc_ref.get()
          co2 = int(doc_temp.get('co2'))
          co2_dest = int(doc_temp.get('co2_dest'))
          if co2 > co2_dest:
               GPIO.output(16,False)         ##릴레이 환기팬 on
               time.sleep(10)
               GPIO.output(16,True)        ##릴레이 환기팬 off
          time.sleep(5)

def func_humidifier():
     while True:
          global doc_temp
          doc_temp = doc_ref.get()
          humidity = int(doc_temp.get('humidity'))
          humidity_dest = int(doc_temp.get('humidity_dest'))
          if humidity < humidity_dest:
               GPIO.output(19,False)         ##릴레이 가습기 on
          else:                
               GPIO.output(19,True)        ##릴레이 가습기 off
          time.sleep(5)

def func_light():
     while True:
          global doc_temp
          doc_temp = doc_ref.get()
          lux = int(doc_temp.get('lux'))
          lux_dest = int(doc_temp.get('lux_dest'))
          if lux < lux_dest:
               GPIO.output(13,False)         ##릴레이 LED on
          else:
               GPIO.output(13,True)         ##릴레이 LED off
          time.sleep(5)

def func_water_supply():
     while True:
          global doc_temp
          doc_temp = doc_ref.get()
          soil_water = int(doc_temp.get('soil'))
          soil_water_dest = int(doc_temp.get('soil_dest'))
          if soil_water < soil_water_dest:
               GPIO.output(6,False)         ##릴레이 워터펌프 on
               time.sleep(1)                 
               GPIO.output(6,True)        ##릴레이 워터펌프 off
          time.sleep(15)

def image_save():   ## 1시간 마다 사진 촬영후 저장
     while True:
          subprocess.call(['gnome-terminal', '-e', 'libcamera-still -o plant_img.jpg'])
          time.sleep(3600)

def exec_yolo():    ## yolo를 사용해 촬영된 사진의 식물 객체 인식
     while True:
          subprocess.call(['gnome-terminal', '-e', 'python3 /home/jkhRpi/yolov5/detect.py --source /home/jkhRpi/Desktop/plant_img.jpg --weights /home/jkhRpi/yolov5/best_20230428.pt --conf 0.3 --save-txt'])
          time.sleep(3600)

def sensor_upload_data():       ## 센서를 통해 센서값 입력받고 DB에 업로드
    while True:
          h, t = Adafruit_DHT.read_retry(sensor, pin)
          adcValue_soil=read_spi_adc(0)
          soil=100-adcValue_soil*(100/1023)
          adcValue_co2=read_spi_adc(1)
          co2=adcValue_co2*2
          I2C_CH = 1
          BH1750_DEV_ADDR = 0x23   # BH1750 주소
          '''
          측정 모드들
          '''
          CONT_H_RES_MODE     = 0x10
          CONT_H_RES_MODE2    = 0x11
          CONT_L_RES_MODE     = 0x13
          ONETIME_H_RES_MODE  = 0x20
          ONETIME_H_RES_MODE2 = 0x21
          ONETIME_L_RES_MODE  = 0x23

          i2c = smbus.SMBus(I2C_CH)       # 사용할 I2C 채널 라이브러리 생성
          luxBytes = i2c.read_i2c_block_data(BH1750_DEV_ADDR, CONT_H_RES_MODE, 2)      # 측정모드 CONT_H_RES_MODE 로 측정하여 2 바이트 읽어오기 
          lux = int.from_bytes(luxBytes, byteorder='big')     # 바이트 배열을 int로 변환
          doc_ref = db.collection('sensor').document('data') #sensor컬렉션에 data를 문서 명으로 설정
          
          if h is not None and t is not None :
               print("온도 = {0:0.1f}*C 습도 = {1:0.1f}%".format(t, h))
               print("토양수분 : %.1f%%" %(soil))
               print("이산화탄소 농도 : %.2fppm" %co2)
               print("조도 : %d" %(lux))
               time.sleep(2)
               #data 파이어베이스에 업로드
               data = {
               u'humidity': h,
               u'temp': t,
               u'soil': soil,
               u'co2' : co2,
               u'lux' : lux
               }
               doc_ref.update(data)
               print("업로드 완료")
               time.sleep(3)
               
          elif h is None or t is None:
               print("토양수분 : %.1f%%" %(soil))
               print("이산화탄소 농도 : %.2fppm" %co2)
               print("조도 : %d" %(lux))
               print("온습도 센서의 값이 정상적으로 읽히지 않았습니다. 나머지 정보만 업로드합니다.")
               #data 파이어베이스에 업로드
               data = {
               u'soil': soil,
               u'co2' : co2,
               u'lux' : lux
               }
               doc_ref.update(data)
               print("업로드 완료")
               time.sleep(3)



p1 = Process(target=func_temp_control)
p2 = Process(target=func_ventilation)
p3 = Process(target=func_humidifier)
p4 = Process(target=func_light)
p5 = Process(target=func_water_supply)
p6 = Process(target=image_save)
p7 = Process(target=exec_yolo)
p8 = Process(target=sensor_upload_data)


try:
     
     p1.start()
     p2.start()
     p3.start()
     p4.start()
     p5.start()
     p6.start()
     p7.start()
     p8.start()

except KeyboardInterrupt:
     GPIO.setup(19, GPIO.OUT, initial=1)
     GPIO.setup(20, GPIO.OUT, initial=1)
     GPIO.setup(21, GPIO.OUT, initial=1)
     GPIO.setup(26, GPIO.OUT, initial=1)
     GPIO.setup(16, GPIO.OUT, initial=1)
     GPIO.setup(13, GPIO.OUT, initial=1)
     GPIO.setup(6, GPIO.OUT, initial=1)
     GPIO.cleanup()
     pass

