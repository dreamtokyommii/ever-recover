from PyQt6.QtWidgets import QWidget
from PyQt6.QtCore import Qt, QRectF, QSize, QPointF
from PyQt6.QtGui import QPainter, QPen, QFont, QColor


class CircularProgress(QWidget):
    """Simple circular progress indicator (0-100)."""

    def __init__(self, parent=None):
        super().__init__(parent)
        self._value = 0
        self._min_size = 140
        self.setMinimumSize(self._min_size, self._min_size)

    def sizeHint(self) -> QSize:
        return QSize(self._min_size, self._min_size)

    def setValue(self, value: int) -> None:
        self._value = max(0, min(100, int(value)))
        self.update()

    def paintEvent(self, event):
        rect = self.rect()
        side = min(rect.width(), rect.height())
        pad = 6
        radius = (side - pad * 2) / 2

        painter = QPainter(self)
        painter.setRenderHint(QPainter.RenderHint.Antialiasing)

        center = QPointF(rect.center().x(), rect.center().y())
        ellipse_rect = QRectF(
            center.x() - radius,
            center.y() - radius,
            radius * 2,
            radius * 2,
        )

        # Background circle
        bg_pen = QPen(QColor('#2b2f31'))
        bg_pen.setWidth(10)
        painter.setPen(bg_pen)
        painter.drawEllipse(ellipse_rect)

        # Foreground arc
        fg_pen = QPen(QColor('#2a9df4'))
        fg_pen.setWidth(10)
        fg_pen.setCapStyle(Qt.PenCapStyle.RoundCap)
        painter.setPen(fg_pen)

        # Draw arc based on value
        span_angle = int(360.0 * (self._value / 100.0))
        # QPainter uses 16th degrees and counter-clockwise; convert
        start = 90 * 16
        span = -span_angle * 16

        painter.drawArc(ellipse_rect, start, span)

        # Draw text
        painter.setPen(QColor('#e6e6e6'))
        font = QFont()
        font.setPointSize(14)
        font.setBold(True)
        painter.setFont(font)

        text = f"{self._value}%"
        fm = painter.fontMetrics()
        tw = fm.horizontalAdvance(text)
        th = fm.height()
        text_point = QPointF(center.x() - tw / 2, center.y() + th / 4)
        painter.drawText(text_point, text)
