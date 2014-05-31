from gevent.monkey import patch_all
patch_all()
from gevent import Greenlet
from gevent.queue import Queue
from gevent.event import Event
from greenlet import greenlet

import gc
import zmq.green as zmq
import gevent
import logging
import setproctitle
import yaml
import collections
import argparse
import signal


def main():
    parser = argparse.ArgumentParser(description='Run ppreporter!')
    parser.add_argument('config', type=argparse.FileType('r'),
                        help='yaml configuration file to run with')
    args = parser.parse_args()

    # implement some defaults, these are all explained in the example
    # configuration file
    config = dict(zmq_pull={'port': 5557, 'address': '127.0.0.1'},
                  procname='ppreporter',
                  workers=5,
                  term_timeout=5,
                  loggers=[{'type': 'StreamHandler',
                            'level': 'DEBUG'}])
    # override those defaults with a loaded yaml config
    add_config = yaml.load(args.config) or {}

    def update(d, u):
        """ Simple recursive dictionary update """
        for k, v in u.iteritems():
            if isinstance(v, collections.Mapping):
                r = update(d.get(k, {}), v)
                d[k] = r
            else:
                d[k] = u[k]
        return d
    update(config, add_config)

    setproctitle.setproctitle(config['procname'])
    reporter = Reporter(config)
    reporter.run()


class Reporter(object):
    def __init__(self, config):
        self.queue = Queue()
        self.workers = []
        self.puller = None
        self.config = config
        self.handlers = []
        self._exit_signal = None

        for log_cfg in self.config['loggers']:
            ch = getattr(logging, log_cfg['type'])()
            log_level = getattr(logging, log_cfg['level'].upper())
            ch.setLevel(log_level)
            fmt = log_cfg.get('format', '%(asctime)s [%(name)s] [%(levelname)s] %(message)s')
            formatter = logging.Formatter(fmt)
            ch.setFormatter(formatter)

            self.handlers.append((log_cfg.get('listeners'), ch, log_level))

        # announce
        self.logger = self.register_logger('reporter')
        self.logger.info("=" * 80)
        self.logger.info("PowerPool reporter daemon (proctitle={}) starting up..."
                         .format(self.config['procname']))

    def register_logger(self, name):
        named_logger = logging.getLogger(name)
        for listen, ch, level in self.handlers:
            if listen is None or name in listen:
                named_logger.addHandler(ch)
                named_logger.setLevel(level)

        return named_logger

    def run(self):
        self.logger.info("Firing up workers")
        for i in xrange(self.config['workers']):
            worker = Worker(self, i)
            self.workers.append(worker)
            worker.start()

        self.logger.info("Starting zmq puller")
        self.puller = Puller(self)
        self.puller.start()

        gevent.signal(signal.SIGINT, self.exit, "SIGINT")
        gevent.signal(signal.SIGHUP, self.exit, "SIGHUP")

        self._exit_signal = Event()
        self._exit_signal.wait()

        # stop all greenlets
        for gl in self.workers:
            self.logger.info("Requesting stop for {} greenlet".format(gl))
            gl.kill(timeout=self.config['term_timeout'], block=False)

        self.logger.info("Requesting stop for puller")
        self.puller.kill(timeout=self.config['term_timeout'], block=False)

        try:
            if gevent.wait(timeout=self.config['term_timeout']):
                self.logger.info("All threads exited normally")
            else:
                self.logger.info("Timeout reached, shutting down forcefully")
        except KeyboardInterrupt:
            self.logger.info("Shutdown requested again by system, "
                             "exiting without cleanup")

        self.logger.info("=" * 80)

    def exit(self, signal=None):
        self.logger.info("*" * 80)
        self.logger.info("Exiting requested via {}, allowing {} seconds for cleanup."
                         .format(signal, self.config['term_timeout']))
        self._exit_signal.set()


class Worker(Greenlet):
    def __init__(self, reporter, id):
        Greenlet.__init__(self)
        self.reporter = reporter
        self.queue = reporter.queue
        self.id = id
        self.logger = reporter.register_logger('worker{}'.format(self.id))

    def _run(self):
        self.logger.info("Starting worker")
        while True:
            dat = self.queue.get()
            self.logger.info("got {}".format(dat, self.id))
            #getattr(self, dat[0])(*dat[1:])


class Puller(Greenlet):
    def __init__(self, reporter):
        Greenlet.__init__(self)
        self.reporter = reporter
        self.queue = reporter.queue
        self.config = reporter.config
        self.logger = reporter.register_logger('puller')
        self.context = None

    def kill(self, *args, **kwargs):
        """ Override our default kill method and kill our child greenlets as
        well """
        self.context.term()
        Greenlet.kill(self, *args, **kwargs)

    def _run(self):
        address = "tcp://{address}:{port}".format(**self.config['zmq_pull'])
        self.logger.info("Listening for zmq PUSH connections on {}".format(address))
        self.context = zmq.Context()
        results_receiver = self.context.socket(zmq.PULL)
        results_receiver.bind(address)

        while True:
            self.queue.put(results_receiver.recv_json())
