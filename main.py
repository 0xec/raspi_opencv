from picamera import PiCamera
from picamera.array import PiRGBArray
import cv2
import time
import tornado.ioloop
import tornado.web
import os

class Camera:
    def __init__(self):
        self.camera = PiCamera()
        self.buffer = PiRGBArray(self.camera)
        self.prev_frame = None

    def set_resolution(self, res):
        self.camera.resolution = res

    def read(self):
        self.buffer.seek(0)
        self.buffer.truncate()
        self.camera.capture(self.buffer, 'bgr', use_video_port=True)
        return self.buffer.array

    def capture_frame(self):
        frame = self.read()
        frame = cv2.flip(frame, -1)
        return frame

    def encode_image(self, frame):
        ret, data = cv2.imencode('.jpg', frame)
        if ret:
            return data.data
        else:
            return None

    def start_preview(self):
        self.camera.start_preview()

    def stop_preview(self):
        self.camera.stop_preview()

    def detect(self, gauss):
        frame = self.capture_frame()

        current_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        current_frame = cv2.GaussianBlur(current_frame, (gauss, gauss), 0)

        status = 'No Detected'
        detected = False
        if self.prev_frame != None:
            frame_delta = cv2.absdiff(current_frame, self.prev_frame)
            self.prev_frame = current_frame
            thresh = cv2.threshold(frame_delta, 25, 255, cv2.THRESH_BINARY)[1]
            thresh = cv2.dilate(thresh, None, iterations=2)
            (cnts, _) = cv2.findContours(thresh.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            for c in cnts:
                # if the contour is too small, ignore it
                if cv2.contourArea(c) < 10.0:
                    continue

                (x, y, w, h) = cv2.boundingRect(c)
                cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)

                detected = True
                status = 'Detected'
        else:
            self.prev_frame = current_frame

        cv2.putText(frame, "Status: {0}".format(status), (10, 15), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 255), 2)
        _, w, _ = frame.shape
        cv2.putText(frame, time.strftime('%Y-%m-%d %H:%M:%S', time.localtime()), (w / 2, 15), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (255, 255, 255), 2)
        return detected, frame

cam = Camera()
cam.set_resolution((1024, 768))
cam.start_preview()
tick = 0
file_tick = 0
preview_frame = None
_, result_frame = cam.detect(11)

class MJPEGHandler(tornado.web.RequestHandler):
    @tornado.web.asynchronous
    @tornado.gen.coroutine
    def get(self):
        global tick
        ioloop = tornado.ioloop.IOLoop.current()
        value = int(self.get_argument('gauss', 11))
        self.set_header('Cache-Control', 'no-store, no-cache, must-revalidate, pre-check=0, post-check=0, max-age=0')
        self.set_header('Connection', 'close')
        self.set_header('Content-Type', 'multipart/x-mixed-replace;boundary=--boundarydonotcross')
        self.set_header('Expires', 'Mon, 3 Jan 2000 12:34:56 GMT')
        self.set_header('Pragma', 'no-cache')

        self.served_image_timestamp = time.time()
        my_boundary = "--boundarydonotcross\n"
        while True:
            # print('frame %d' % tick)
            tick += 1
            interval = 0.1
            preview = ''

            if preview_frame != None:
                preview = cam.encode_image(preview_frame)

            if self.served_image_timestamp + interval < time.time():
                self.write(my_boundary)
                self.write("Content-type: image/jpeg\r\n")
                self.write("Content-length: %s\r\n\r\n" % len(preview))
                self.write(str(preview))
                self.served_image_timestamp = time.time()
                yield tornado.gen.Task(self.flush)
            else:
                yield tornado.gen.Task(ioloop.add_timeout, ioloop.time() + interval)


class ImageHandler(tornado.web.RequestHandler):
    def get(self):
        self.set_header("Content-type", "image/jpeg")
        frame = cam.detect()
        print(len(frame))
        self.write(str(frame))


def make_app():
    return tornado.web.Application([
        (r"/preview", MJPEGHandler),
    ])

def timer_callback():
    global preview_frame
    global file_tick
    # print('timer callback')
    # print(time.strftime('%Y-%m-%d %H:%M:%S', time.localtime()))
    motion, frame = cam.detect(11)
    preview_frame = frame
    if motion:
        filename = 'motion_%05d.jpg' % file_tick
        cv2.imwrite(filename, frame)
        print('write file: %s' % filename)
        file_tick += 1

    tornado.ioloop.IOLoop.current().call_later(0.2, timer_callback)

if __name__ == "__main__":
    os.system("rm *.jpg")
    app = make_app()
    app.listen(8080)
    timer_callback()
    tornado.ioloop.IOLoop.current().start()


