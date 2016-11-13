from picamera import PiCamera
from picamera.array import PiRGBArray
import cv2
import time
import tornado.ioloop
import tornado.web


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

    def detect(self, gauss):
        frame = self.capture_frame()

        current_frame = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        current_frame = cv2.GaussianBlur(current_frame, (gauss, gauss), 0)

        if self.prev_frame != None:
            frame_delta = cv2.absdiff(current_frame, self.prev_frame)
            self.prev_frame = current_frame
            thresh = cv2.threshold(frame_delta, 25, 255, cv2.THRESH_BINARY)[1]
            thresh = cv2.dilate(thresh, None, iterations=2)
            (cnts, _) = cv2.findContours(thresh.copy(), cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
            for c in cnts:
                # if the contour is too small, ignore it
                if cv2.contourArea(c) < 300.0:
                    continue

                (x, y, w, h) = cv2.boundingRect(c)
                cv2.rectangle(frame, (x, y), (x + w, y + h), (0, 255, 0), 2)
        else:
            self.prev_frame = current_frame

        return self.encode_image(frame)

cam = Camera()
# cam.set_resolution((1280, 800))


class MJPEGHandler(tornado.web.RequestHandler):
    @tornado.web.asynchronous
    @tornado.gen.coroutine
    def get(self):
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
            frame = cam.detect(value)
            interval = 0.05
            if self.served_image_timestamp + interval < time.time():
                self.write(my_boundary)
                self.write("Content-type: image/jpeg\r\n")
                self.write("Content-length: %s\r\n\r\n" % len(frame))
                self.write(str(frame))
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

if __name__ == "__main__":
    app = make_app()
    app.listen(8080)
    tornado.ioloop.IOLoop.current().start()


