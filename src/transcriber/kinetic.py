"""Native Maximalism decoration; legacy class names preserve existing UI imports."""
import os
import math
from pathlib import Path
from PySide6.QtCore import QPointF, QRectF, QVariantAnimation, QEasingCurve, Qt
from PySide6.QtGui import QColor, QPainter, QPolygonF, QLinearGradient, QPen, QIcon, QPixmap, QFont
from PySide6.QtWidgets import QPushButton, QWidget, QFrame
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
        accent = QColor(COLORS['ink'] if self.objectName() in ('primary','exportPrimary') else COLORS['focus'])
        accent.setAlphaF(self._hover*.8)
        painter.setPen(QPen(accent, 2))
        painter.drawLine(QPointF(12,self.height()-4),QPointF(12+(self.width()-24)*self._hover,self.height()-4))


class KineticMark(QWidget):
    """Layered decorative shapes, never a status or audio waveform."""
    def __init__(self, parent=None):
        super().__init__(parent)
        self.setFixedSize(128, 40)
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def paintEvent(self, event):
        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setPen(QPen(QColor(COLORS['ink']), 2))
        painter.setBrush(QColor(COLORS['purple']))
        painter.drawRoundedRect(QRectF(6,10,66,24),5,5)
        painter.setBrush(QColor(COLORS['cyan']))
        painter.drawEllipse(QRectF(47,3,32,32))
        star(painter,99,20,18,COLORS['yellow'])


def star(painter, x, y, radius, color):
    points=[]
    for i in range(16):
        angle=i*math.pi/8
        r=radius if i%2==0 else radius*.48
        points.append(QPointF(x+math.cos(angle)*r,y+math.sin(angle)*r))
    painter.setBrush(QColor(color))
    painter.drawPolygon(QPolygonF(points))


class MaximalCanvas(QWidget):
    def paintEvent(self, event):
        painter=QPainter(self)
        painter.fillRect(self.rect(),QColor(COLORS['canvas']))
        sidebar=getattr(self.window(),'sidebar',None)
        left=sidebar.width() if sidebar else 208
        painter.setPen(QPen(QColor('#DED4C4'),1))
        for x in range(left+12,self.width(),20):
            for y in range(14,self.height(),20):
                painter.drawPoint(x,y)
        gradient=QLinearGradient(left,0,self.width(),0)
        for at,key in [(0,'red'),(.33,'yellow'),(.66,'cyan'),(1,'purple')]:
            gradient.setColorAt(at,QColor(COLORS[key]))
        painter.fillRect(QRectF(left,0,self.width()-left,8),gradient)


class MaximalPanel(QFrame):
    """Two offset paper shadows contained inside the widget's geometry."""
    def paintEvent(self, event):
        painter=QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        rect=QRectF(self.rect()).adjusted(5,5,-8,-8)
        painter.setPen(Qt.PenStyle.NoPen)
        painter.setBrush(QColor(COLORS['cyan']))
        painter.drawRoundedRect(rect.translated(-4,-4),12,12)
        painter.setBrush(QColor(COLORS['red']))
        painter.drawRoundedRect(rect.translated(6,6),12,12)
        active=bool(self.property('dropActive'))
        painter.setPen(QPen(QColor(COLORS['primary'] if active else COLORS['ink']),2))
        painter.setBrush(QColor(COLORS['selection'] if active else COLORS['white']))
        painter.drawRoundedRect(rect,12,12)


class VoiceCollage(QWidget):
    """A decorative empty-state collage using the user's exact icon."""
    def __init__(self,parent=None):
        super().__init__(parent)
        self.setMinimumHeight(70)
        self.setMaximumHeight(150)
        self.icon=QPixmap(str(Path(__file__).parent/'assets/app.png'))
        self.setAttribute(Qt.WidgetAttribute.WA_TransparentForMouseEvents)

    def paintEvent(self,event):
        painter=QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)
        painter.setRenderHint(QPainter.RenderHint.SmoothPixmapTransform)
        painter.translate(self.width()/2,self.height()/2)
        scale=min(1.,self.width()/400,self.height()/140)
        painter.scale(scale,scale)
        painter.setPen(QPen(QColor(COLORS['ink']),2))
        painter.setBrush(QColor(COLORS['purple']))
        painter.drawRoundedRect(QRectF(-67,-46,142,103),12,12)
        painter.drawPixmap(-69,-59,126,126,self.icon)
        for x,y,angle,text,key,width in [(-178,-33,-9,'VOICE → TEXT','yellow',130),(55,21,8,'LOCAL FIRST','cyan',126)]:
            painter.save();painter.translate(x,y);painter.rotate(angle)
            painter.setBrush(QColor(COLORS[key]));painter.drawRoundedRect(QRectF(0,0,width,32),4,4)
            font=QFont('Segoe UI');font.setPixelSize(13);font.setBold(True);painter.setFont(font)
            painter.drawText(QRectF(0,0,width,32),Qt.AlignmentFlag.AlignCenter,text)
            painter.restore()
        star(painter,106,-40,22,COLORS['red'])
        star(painter,-113,44,17,COLORS['purple'])
