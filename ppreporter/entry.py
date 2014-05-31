import zmq
import multiprocessing
import logging
logging.getLogger().addHandler(logging.StreamHandler())


class Worker(multiprocessing.Process):
    def __init__(self, queue, id):
        multiprocessing.Process.__init__(self)
        self.queue = queue
        self.id = id

    def run(self):
        while True:
            dat = self.queue.get()
            logging.info("got {} on process {}".format(dat, self.id))
            #getattr(self, dat[0])(*dat[1:])


def main():
    queue = multiprocessing.Queue()
    workers = []

    for i in xrange(5):
        worker = Worker(queue, i)
        workers.append(worker)
        worker.start()

    context = zmq.Context()
    results_receiver = context.socket(zmq.PULL)
    results_receiver.bind("tcp://127.0.0.1:5557")

    while True:
        queue.put(results_receiver.recv_json())
