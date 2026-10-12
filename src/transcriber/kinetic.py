"""Small native Kinetic accents. Nothing moves the reading layout."""
import os
from PySide6.QtCore import QPointF, QVariantAnimation, QEasingCurve, Qt
from PySide6.QtGui import QColor, QPainter, QPolygonF, QLinearGradient, QPen, QIcon, QPixmap
from PySide6.QtWidgets import QPushButton, QWidget
from .theme import COLORS


def playback_icon(paused=False):
    pixmap = QPixmap(32,32)
    pixmap.fill(Qt.GlobalColor.transparent)
    painter = QPainter(pixmap)
    painter.setRenderHint(QPainter.RenderHint.Antialiasing)
    painter.setPen(Qt.PenStyle.NoPen)
    painter.setBrush(QColor(COLORS['on_accent']))
    if paused:
        painter.drawRect(8,6,5,20)
        painter.drawRect(19,6,5,20)
    else:
        painter.drawPolygon(QPolygonF([QPointF(9,5),QPointF(9,27),QPointF(26,16)]))
    painter.end()
    return QIcon(pixmap)


def motion_enabled():
    if os.environ.get('TRANSCRIBER_REDUCE_MOTION') == '1':
        return False
    if os.name == 'nt':
        try:
            import ctypes
            enabled = ctypes.c_int(1)
            if ctypes.windll.user32.SystemParametersInfoW(0x1042, 0, ctypes.byref(enabled), 0):
                return bool(enabled.value)  # Windows client-area animation preference.
        except (AttributeError, OSError):
            pass
    return True


class KineticButton(QPushButton):
    def __init__(self, text, parent=None):
        super().__init__(text, parent)
        self._hover = 0.
        self._motion = motion_enabled()
        self._animation = QVariantAnimation(self)
        self._animation.setDuration(160)
        self._animation.setEasingCurve(QEasingCurve.Type.OutCubic)
        self._animation.valueChanged.connect(self._set_hover)

    def _set_hover(self, value):
        self._hover = float(value)
        self.update()

    def _animate(self, value):
        self._animation.stop()
        if not self._motion:
            self._set_hover(value)
            return
        self._animation.setStartValue(self._hover)
        self._animation.setEndValue(value)
        self._animation.start()

    def enterEvent(self, event):
        super().enterEvent(event)
        if self.isEnabled():
            self._animate(1.)

    def leaveEvent(self, event):
        super().leaveEvent(event)
        self._animate(0.)

    def paintEvent(self, event):
        super().paintEvent(event)
        if self._hover <= .01 or not self.isEnabled():
            return
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        accent = QColor(COLORS['on_accent'] if self.objectName() in ('primary','exportPrimary') else COLORS['orange'])
        accent.setAlphaF(self._hover*.8)
        painter.setPen(QPen(accent, 2))
        painter.drawLine(QPointF(12,self.height()-4),QPointF(12+(self.width()-24)*self._hover,self.height()-4))


class KineticMark(QWidget):
    """Diagonal signature; deliberately decorative, never an audio waveform."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(112, 32)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(Qt.PenStyle.NoPen)
        for i in range(5):
            x = i*22
            gradient = QLinearGradient(x,0,x+20,self.height())
            red, orange = QColor(COLORS['red']), QColor(COLORS['orange'])
            red.setAlphaF(1-i*.17)
            orange.setAlphaF(1-i*.17)
            gradient.setColorAt(0,red)
            gradient.setColorAt(1,orange)
            painter.setBrush(gradient)
            painter.drawPolygon(QPolygonF([QPointF(x+14,0),QPointF(x+22,0),
                                           QPointF(x+8,self.height()),QPointF(x,self.height())]))
