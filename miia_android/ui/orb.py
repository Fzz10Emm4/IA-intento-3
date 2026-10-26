"""La esfera animada de MIIA (la misma del PC, dibujada con mallas de Kivy)."""

import math
import random
import time

from kivy.clock import Clock
from kivy.graphics import Color, Ellipse, Mesh
from kivy.uix.widget import Widget

from . import theme
from .theme import rgba

POINTS = 56


class Orb(Widget):
    def __init__(self, **kw):
        super().__init__(**kw)
        self.speaking = False
        self.thinking = False
        self.listening = False
        self.energy = 0.0
        self.target = 0.0
        self.angle = 0.0
        self.r = 40.0
        self.base_r = 40.0
        self.p1, self.p2, self.p3 = (random.uniform(0, math.tau) for _ in range(3))
        self._ev = None
        self._rate = 1 / 30.0
        self._indices = list(range(POINTS + 2))
        self.meshes = []
        with self.canvas:
            for _rel, col in theme.ORB_LAYERS:
                Color(*rgba(col))
                self.meshes.append(Mesh(vertices=[0.0] * ((POINTS + 2) * 4), indices=self._indices,
                                        mode="triangle_fan"))
            Color(0, 0, 0, 1)
            self.core = Ellipse(pos=(0, 0), size=(0, 0))
        self.bind(size=self._resize, pos=self._resize)
        self._resize()

    # ---- estado ----
    def set_state(self, speaking=None, thinking=None, listening=None):
        if speaking is not None:
            self.speaking = speaking
        if thinking is not None:
            self.thinking = thinking
        if listening is not None:
            self.listening = listening
        self.target = 1.0 if self.speaking else (0.55 if self.listening else (0.3 if self.thinking else 0.0))
        self._want_rate()

    def start(self):
        if self._ev is None:
            self._ev = Clock.schedule_interval(self._tick, self._rate)

    def stop(self):
        if self._ev is not None:
            self._ev.cancel()
            self._ev = None

    def _want_rate(self):
        rate = 1 / 30.0 if (self.target > 0 or self.energy > 0.03) else 1 / 12.0
        if rate != self._rate:
            self._rate = rate
            if self._ev is not None:
                self._ev.cancel()
                self._ev = Clock.schedule_interval(self._tick, rate)

    def _resize(self, *_):
        self.base_r = max(20.0, min(self.width, self.height) * 0.5 / 1.62)
        self.r = self.base_r
        self._draw()

    # ---- animación ----
    def _tick(self, dt):
        smoothing = 0.115 if self.speaking else 0.055
        self.energy += (self.target - self.energy) * smoothing
        now = time.perf_counter()
        self.angle += 0.0018 + self.energy * 0.009
        pulse = (0.012 * math.sin(now * 1.35) +
                 self.energy * (0.018 + 0.020 * math.sin(now * 6.0) + 0.010 * math.sin(now * 10.5)))
        target_r = self.base_r * (1.0 + pulse)
        self.r += (target_r - self.r) * 0.12
        self._draw()
        if self.target == 0 and self.energy < 0.03:
            self._want_rate()

    def _ring(self, cx, cy, radius, layer_i, t):
        e = self.energy
        n = len(theme.ORB_LAYERS)
        reaction = max(0.0, 1.0 - layer_i / n)
        out = [cx, cy, 0.0, 0.0]
        for i in range(POINTS + 1):
            a = math.tau * (i % POINTS) / POINTS + self.angle
            wave = (math.sin(a * 2.0 + self.p1) * 0.48 + math.sin(a * 3.0 - self.p2) * 0.25 +
                    math.sin(a * 5.0 + self.p3) * 0.12)
            voice = math.sin(t * 8.0 + a * 2.0 + self.p1) * 0.34 + math.sin(t * 12.5 - a * 3.0 + self.p2) * 0.16
            deform = wave * e * radius * 0.055 + voice * e * radius * 0.032
            rr = radius + deform * (0.55 + reaction * 0.45)
            out.extend((cx + math.cos(a) * rr, cy + math.sin(a) * rr, 0.0, 0.0))
        return out

    def _draw(self):
        cx, cy = self.center_x, self.center_y
        t = time.perf_counter()
        for i, (rel, _col) in enumerate(theme.ORB_LAYERS):
            self.meshes[i].vertices = self._ring(cx, cy, self.r * rel, i, t)
        core_r = self.r * (0.70 + self.energy * 0.025)
        self.core.pos = (cx - core_r, cy - core_r)
        self.core.size = (core_r * 2, core_r * 2)
