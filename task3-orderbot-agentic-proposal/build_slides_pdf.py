#!/usr/bin/env python3
"""
Generates a crisp, 16:9 executive 3-slide vector PDF presentation for Datacom Task 3:
"OrderBot: Automating Hardware Order Processing with Agentic AI".

Uses pure Python + Ghostscript (gs) to emit exact vector shapes, flowcharts,
color-coded callouts, and Helvetica typography with zero external Python dependencies.
"""

import math
import os
import subprocess
from typing import List, Optional, Tuple

W = 960.0  # 13.333 in * 72 pt/in (16:9 widescreen)
H = 540.0  # 7.5 in * 72 pt/in

# Datacom Executive Palette
NAVY = (0.039, 0.145, 0.251)        # #0A2540
NAVY_MID = (0.051, 0.231, 0.400)    # #0D3B66
BLUE = (0.000, 0.341, 0.722)        # #0057B8
BLUE_LIGHT = (0.937, 0.965, 1.000)  # #EFF6FF
BLUE_BORDER = (0.576, 0.773, 0.992) # #93C5FD
CYAN_LIGHT = (0.878, 0.949, 0.996)  # #E0F2FE
CYAN_DARK = (0.012, 0.412, 0.631)   # #0369A1

RED = (0.863, 0.149, 0.149)         # #DC2626
RED_DARK = (0.600, 0.106, 0.106)    # #991B1B
RED_BG = (1.000, 0.961, 0.961)      # #FFF5F5
RED_TINT = (0.996, 0.886, 0.886)    # #FEE2E2
RED_BORDER = (0.988, 0.647, 0.647)  # #FCA5A5

GREEN = (0.020, 0.588, 0.412)       # #059669
GREEN_DARK = (0.024, 0.373, 0.275)  # #065F46
GREEN_BG = (0.941, 0.992, 0.957)    # #F0FDF4
GREEN_TINT = (0.863, 0.988, 0.906)  # #DCFCE7
GREEN_BORDER = (0.525, 0.937, 0.675)# #86EFAC
MINT = (0.204, 0.827, 0.600)        # #34D399

AMBER = (0.851, 0.467, 0.024)       # #D97706
AMBER_DARK = (0.573, 0.251, 0.055)  # #92400E
AMBER_BG = (1.000, 0.984, 0.922)    # #FFFBEB
AMBER_TINT = (0.996, 0.953, 0.780)  # #FEF3C7

SLATE_900 = (0.059, 0.090, 0.165)   # #0F172A
SLATE_700 = (0.200, 0.255, 0.333)   # #334155
SLATE_600 = (0.278, 0.333, 0.412)   # #475569
SLATE_500 = (0.392, 0.455, 0.545)   # #64748B
SLATE_300 = (0.796, 0.835, 0.882)   # #CBD5E1
SLATE_200 = (0.886, 0.910, 0.941)   # #E2E8F0
SLATE_100 = (0.945, 0.961, 0.976)   # #F1F5F9
SLATE_50 = (0.973, 0.980, 0.988)    # #F8FAFC
WHITE = (1.0, 1.0, 1.0)


def _ps_escape(text: str) -> str:
    """Escape text for PostScript literal strings (ASCII-safe Latin-1)."""
    replacements = {
        "→": "->",
        "—": "-",
        "–": "-",
        "·": "-",
        "•": "*",
        "≥": ">=",
        "≤": "<=",
        "★": "*",
        "’": "'",
        "‘": "'",
        "“": '"',
        "”": '"',
    }
    for k, v in replacements.items():
        text = text.replace(k, v)
    return text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")


def _approx_width(text: str, size: float, bold: bool = False) -> float:
    """Estimate Helvetica text width in points for clean wrapping."""
    narrow = set("ijlI1.,;:'!|()[]/ ")
    wide = set("MWmw@#%&")
    total = 0.0
    for ch in text:
        if ch in narrow:
            total += 0.29
        elif ch in wide:
            total += 0.82
        elif ch.isupper():
            total += 0.67
        else:
            total += 0.52
    factor = 1.05 if bold else 1.0
    return total * size * factor


def _wrap_lines(text: str, max_w: float, size: float, bold: bool = False) -> List[str]:
    words = text.split()
    if not words:
        return []
    lines: List[str] = []
    cur = words[0]
    for word in words[1:]:
        candidate = f"{cur} {word}"
        if _approx_width(candidate, size, bold) <= max_w:
            cur = candidate
        else:
            lines.append(cur)
            cur = word
    lines.append(cur)
    return lines


class SlidePage:
    """Top-down PostScript vector drawing helper for a single 960x540 slide."""

    def __init__(self) -> None:
        self.cmds: List[str] = []

    def _y(self, y: float) -> float:
        return H - y

    def _rgb(self, c: Tuple[float, float, float]) -> str:
        return f"{c[0]:.3f} {c[1]:.3f} {c[2]:.3f} setrgbcolor"

    def _rrect_path(self, x: float, y: float, w: float, h: float, r: float) -> None:
        y_bot = self._y(y + h)
        r = min(r, w / 2.0, h / 2.0)
        if r <= 0.1:
            self.cmds.append(f"newpath {x:.2f} {y_bot:.2f} {w:.2f} {h:.2f} rectpath")
        else:
            self.cmds.append(
                f"newpath "
                f"{x + r:.2f} {y_bot:.2f} moveto "
                f"{x + w:.2f} {y_bot:.2f} {x + w:.2f} {y_bot + h:.2f} {r:.2f} arct "
                f"{x + w:.2f} {y_bot + h:.2f} {x:.2f} {y_bot + h:.2f} {r:.2f} arct "
                f"{x:.2f} {y_bot + h:.2f} {x:.2f} {y_bot:.2f} {r:.2f} arct "
                f"{x:.2f} {y_bot:.2f} {x + w:.2f} {y_bot:.2f} {r:.2f} arct closepath"
            )

    def fill_rect(
        self, x: float, y: float, w: float, h: float, color: Tuple[float, float, float], r: float = 0.0
    ) -> None:
        self.cmds.append("gsave")
        self.cmds.append(self._rgb(color))
        if r <= 0.1:
            self.cmds.append(f"{x:.2f} {self._y(y + h):.2f} {w:.2f} {h:.2f} rectfill")
        else:
            self._rrect_path(x, y, w, h, r)
            self.cmds.append("fill")
        self.cmds.append("grestore")

    def stroke_rect(
        self,
        x: float,
        y: float,
        w: float,
        h: float,
        color: Tuple[float, float, float],
        lw: float = 1.2,
        r: float = 0.0,
        dash: Optional[str] = None,
    ) -> None:
        self.cmds.append("gsave")
        self.cmds.append(self._rgb(color))
        self.cmds.append(f"{lw:.2f} setlinewidth")
        if dash:
            self.cmds.append(f"[{dash}] 0 setdash")
        if r <= 0.1:
            self.cmds.append(f"{x:.2f} {self._y(y + h):.2f} {w:.2f} {h:.2f} rectstroke")
        else:
            self._rrect_path(x, y, w, h, r)
            self.cmds.append("stroke")
        self.cmds.append("grestore")

    def card(
        self,
        x: float,
        y: float,
        w: float,
        h: float,
        fill: Tuple[float, float, float] = WHITE,
        stroke: Tuple[float, float, float] = SLATE_200,
        r: float = 8.0,
        lw: float = 1.1,
        top_bar: Optional[Tuple[float, float, float]] = None,
        top_bar_h: float = 4.0,
        left_bar: Optional[Tuple[float, float, float]] = None,
        left_bar_w: float = 4.0,
    ) -> None:
        self.fill_rect(x, y, w, h, fill, r=r)
        if top_bar is not None:
            self.cmds.append("gsave")
            self._rrect_path(x, y, w, h, r)
            self.cmds.append("clip")
            self.fill_rect(x, y, w, top_bar_h, top_bar, r=0)
            self.cmds.append("grestore")
        if left_bar is not None:
            self.cmds.append("gsave")
            self._rrect_path(x, y, w, h, r)
            self.cmds.append("clip")
            self.fill_rect(x, y, left_bar_w, h, left_bar, r=0)
            self.cmds.append("grestore")
        self.stroke_rect(x, y, w, h, stroke, lw=lw, r=r)

    def circle(self, cx: float, cy: float, radius: float, color: Tuple[float, float, float]) -> None:
        self.cmds.append("gsave")
        self.cmds.append(self._rgb(color))
        self.cmds.append(f"newpath {cx:.2f} {self._y(cy):.2f} {radius:.2f} 0 360 arc fill")
        self.cmds.append("grestore")

    def diamond(
        self,
        cx: float,
        cy: float,
        rx: float,
        ry: float,
        fill: Tuple[float, float, float],
        stroke: Tuple[float, float, float],
        lw: float = 1.8,
    ) -> None:
        pts = [
            (cx, self._y(cy - ry)),
            (cx + rx, self._y(cy)),
            (cx, self._y(cy + ry)),
            (cx - rx, self._y(cy)),
        ]
        self.cmds.append("gsave")
        path = (
            f"newpath {pts[0][0]:.2f} {pts[0][1]:.2f} moveto "
            f"{pts[1][0]:.2f} {pts[1][1]:.2f} lineto "
            f"{pts[2][0]:.2f} {pts[2][1]:.2f} lineto "
            f"{pts[3][0]:.2f} {pts[3][1]:.2f} lineto closepath"
        )
        self.cmds.append(path)
        self.cmds.append(self._rgb(fill))
        self.cmds.append("gsave fill grestore")
        self.cmds.append(self._rgb(stroke))
        self.cmds.append(f"{lw:.2f} setlinewidth stroke")
        self.cmds.append("grestore")

    def poly_arrow(
        self,
        points: List[Tuple[float, float]],
        color: Tuple[float, float, float],
        lw: float = 1.6,
        dash: Optional[str] = None,
        head_size: float = 6.5,
    ) -> None:
        if len(points) < 2:
            return
        self.cmds.append("gsave")
        self.cmds.append(self._rgb(color))
        self.cmds.append(f"{lw:.2f} setlinewidth 1 setlinejoin 1 setlinecap")
        if dash:
            self.cmds.append(f"[{dash}] 0 setdash")

        x_prev, y_prev = points[-2]
        x_end, y_end = points[-1]
        dx = x_end - x_prev
        dy = y_end - y_prev
        dist = math.hypot(dx, dy) or 1.0
        ux, uy = dx / dist, dy / dist
        line_end_x = x_end - ux * (head_size * 0.7)
        line_end_y = y_end - uy * (head_size * 0.7)

        self.cmds.append(f"newpath {points[0][0]:.2f} {self._y(points[0][1]):.2f} moveto")
        for px, py in points[1:-1]:
            self.cmds.append(f"{px:.2f} {self._y(py):.2f} lineto")
        self.cmds.append(f"{line_end_x:.2f} {self._y(line_end_y):.2f} lineto stroke")
        self.cmds.append("grestore")

        # Solid arrowhead
        px1 = x_end - ux * head_size - uy * (head_size * 0.48)
        py1 = y_end - uy * head_size + ux * (head_size * 0.48)
        px2 = x_end - ux * head_size + uy * (head_size * 0.48)
        py2 = y_end - uy * head_size - ux * (head_size * 0.48)
        self.cmds.append("gsave")
        self.cmds.append(self._rgb(color))
        self.cmds.append(
            f"newpath {x_end:.2f} {self._y(y_end):.2f} moveto "
            f"{px1:.2f} {self._y(py1):.2f} lineto "
            f"{px2:.2f} {self._y(py2):.2f} lineto closepath fill"
        )
        self.cmds.append("grestore")

    def text(
        self,
        x: float,
        y: float,
        s: str,
        size: float = 10.5,
        bold: bool = False,
        color: Tuple[float, float, float] = SLATE_900,
        align: str = "left",
    ) -> None:
        font = "Helvetica-Bold" if bold else "Helvetica"
        esc = _ps_escape(s)
        ps_y = self._y(y)
        self.cmds.append("gsave")
        self.cmds.append(f"/{font} findfont {size:.2f} scalefont setfont")
        self.cmds.append(self._rgb(color))
        if align == "center":
            self.cmds.append(
                f"({esc}) dup stringwidth pop 2 div {x:.2f} exch sub {ps_y:.2f} moveto show"
            )
        elif align == "right":
            self.cmds.append(
                f"({esc}) dup stringwidth pop {x:.2f} exch sub {ps_y:.2f} moveto show"
            )
        else:
            self.cmds.append(f"{x:.2f} {ps_y:.2f} moveto ({esc}) show")
        self.cmds.append("grestore")

    def wrapped_text(
        self,
        x: float,
        y: float,
        max_w: float,
        s: str,
        size: float = 9.5,
        bold: bool = False,
        color: Tuple[float, float, float] = SLATE_600,
        line_h: float = 13.0,
        align: str = "left",
    ) -> float:
        lines = _wrap_lines(s, max_w, size, bold)
        cur_y = y
        for line in lines:
            self.text(x, cur_y, line, size=size, bold=bold, color=color, align=align)
            cur_y += line_h
        return cur_y

    def pill(
        self,
        x: float,
        y: float,
        w: float,
        h: float,
        label: str,
        bg: Tuple[float, float, float],
        fg: Tuple[float, float, float],
        size: float = 8.0,
        bold: bool = True,
        stroke: Optional[Tuple[float, float, float]] = None,
    ) -> None:
        self.fill_rect(x, y, w, h, bg, r=h / 2.0)
        if stroke is not None:
            self.stroke_rect(x, y, w, h, stroke, lw=0.8, r=h / 2.0)
        self.text(x + w / 2.0, y + h * 0.70, label, size=size, bold=bold, color=fg, align="center")

    def header_and_footer(
        self, eyebrow: str, eyebrow_bg: Tuple[float, float, float], eyebrow_fg: Tuple[float, float, float], title: str, page_num: int
    ) -> None:
        # Top navy header
        self.fill_rect(0, 0, W, 72, NAVY)
        self.fill_rect(0, 70, W, 2.5, BLUE)
        self.pill(36, 14, len(eyebrow) * 5.2 + 20, 17, eyebrow, eyebrow_bg, eyebrow_fg, size=7.8)
        self.text(36, 56, title, size=19.5, bold=True, color=WHITE)

        # Right brand mark
        self.text(W - 36, 31, "DATACOM", size=12, bold=True, color=WHITE, align="right")
        self.text(
            W - 36, 46, "Operations Automation Proposal", size=8.8, bold=False, color=SLATE_300, align="right"
        )

        # Bottom footer
        self.fill_rect(0, H - 28, W, 28, SLATE_50)
        self.fill_rect(0, H - 28, W, 1, SLATE_200)
        self.text(
            36, H - 10, "Datacom Operations  |  Hardware Order Processing Automation (OrderBot)", size=8.2, color=SLATE_500
        )
        self.text(W - 36, H - 10, f"Slide {page_num} / 3", size=8.5, bold=True, color=NAVY, align="right")

    def render(self) -> str:
        return "\n".join(self.cmds) + "\nshowpage\n"


def build_slide_1() -> SlidePage:
    """Slide 1: The Problem - Current Manual Order Process Is a Bottleneck."""
    s = SlidePage()
    s.fill_rect(0, 0, W, H, WHITE)
    s.header_and_footer(
        "SLIDE 1  -  CURRENT STATE ANALYSIS",
        (0.55, 0.14, 0.18),
        (1.0, 0.85, 0.85),
        "The Problem: Our Manual Hardware Order Process Is a Bottleneck",
        1,
    )

    # Flowchart Container
    s.card(36, 86, 888, 212, fill=SLATE_50, stroke=SLATE_200, r=10)
    s.circle(54, 102, 4, RED)
    s.text(64, 106, "CURRENT MANUAL WORKFLOW  -  DISCONNECTED SYSTEMS & FAILURE POINTS", size=9.2, bold=True, color=SLATE_700)

    # Step boxes y=132, h=78
    box_y = 134
    box_h = 74

    # Step 1
    s.card(50, box_y, 122, box_h, fill=WHITE, stroke=SLATE_300, r=8, top_bar=SLATE_200, top_bar_h=20)
    s.text(111, box_y + 13.5, "1. EMAIL INTAKE", size=8.0, bold=True, color=SLATE_700, align="center")
    s.text(111, box_y + 34, "Sales Rep Emails", size=9.2, bold=True, color=SLATE_900, align="center")
    s.text(111, box_y + 48, "PDF Order Form to", size=8.4, color=SLATE_600, align="center")
    s.text(111, box_y + 61, "Shared Inbox", size=8.4, color=SLATE_600, align="center")
    s.pill(69, box_y + 80, 84, 16, "System: Email", SLATE_100, SLATE_700, size=7.5, stroke=SLATE_300)

    s.poly_arrow([(172, box_y + 37), (196, box_y + 37)], SLATE_500)

    # Step 2 (Red Bottleneck)
    s.pill(210, 114, 96, 16, "! Copy-Paste Errors", RED, WHITE, size=7.5)
    s.card(198, box_y, 122, box_h, fill=RED_BG, stroke=RED, r=8, lw=1.6, top_bar=RED_TINT, top_bar_h=20)
    s.text(259, box_y + 13.5, "2. MANUAL READ", size=8.0, bold=True, color=RED_DARK, align="center")
    s.text(259, box_y + 34, "Ops Reads PDF", size=9.2, bold=True, color=SLATE_900, align="center")
    s.text(259, box_y + 48, "Manually extracts", size=8.4, color=SLATE_600, align="center")
    s.text(259, box_y + 61, "SKUs, qty & client", size=8.4, color=SLATE_600, align="center")
    s.pill(212, box_y + 80, 94, 16, "~15-20 min / order", RED_BG, RED_DARK, size=7.5, stroke=RED_BORDER)

    s.poly_arrow([(320, box_y + 37), (344, box_y + 37)], RED)

    # Step 3
    s.card(346, box_y, 122, box_h, fill=RED_BG, stroke=RED, r=8, lw=1.6, top_bar=RED_TINT, top_bar_h=20)
    s.text(407, box_y + 13.5, "3. ACCOUNT CHECK", size=8.0, bold=True, color=RED_DARK, align="center")
    s.text(407, box_y + 34, "Manual Lookup", size=9.2, bold=True, color=SLATE_900, align="center")
    s.text(407, box_y + 48, "Verify credit &", size=8.4, color=SLATE_600, align="center")
    s.text(407, box_y + 61, "account status", size=8.4, color=SLATE_600, align="center")
    s.pill(357, box_y + 80, 100, 16, "System: Salesforce", CYAN_LIGHT, CYAN_DARK, size=7.5, stroke=BLUE_BORDER)

    s.poly_arrow([(468, box_y + 37), (492, box_y + 37)], RED)

    # Step 4
    s.pill(504, 114, 102, 16, "! Stale Stock Risk", RED, WHITE, size=7.5)
    s.card(494, box_y, 122, box_h, fill=RED_BG, stroke=RED, r=8, lw=1.6, top_bar=RED_TINT, top_bar_h=20)
    s.text(555, box_y + 13.5, "4. STOCK CHECK", size=8.0, bold=True, color=RED_DARK, align="center")
    s.text(555, box_y + 34, "Manual Sheet Scan", size=9.2, bold=True, color=SLATE_900, align="center")
    s.text(555, box_y + 48, "Check stock levels", size=8.4, color=SLATE_600, align="center")
    s.text(555, box_y + 61, "& edit by hand", size=8.4, color=SLATE_600, align="center")
    s.pill(500, box_y + 80, 110, 16, "System: Google Sheets", GREEN_TINT, GREEN_DARK, size=7.3, stroke=GREEN_BORDER)

    s.poly_arrow([(616, box_y + 37), (642, box_y + 37)], SLATE_500)

    # Step 5 Decision Diamond
    s.diamond(684, box_y + 37, 40, 38, AMBER_BG, AMBER, lw=1.8)
    s.text(684, box_y + 34, "5. All", size=8.8, bold=True, color=AMBER_DARK, align="center")
    s.text(684, box_y + 46, "Valid?", size=8.8, bold=True, color=AMBER_DARK, align="center")

    # YES path
    s.poly_arrow([(724, box_y + 37), (744, box_y + 37), (744, 146), (762, 146)], SLATE_700)
    s.text(742, 139, "YES", size=7.8, bold=True, color=SLATE_700, align="center")
    s.card(764, 118, 146, 56, fill=WHITE, stroke=SLATE_500, r=8, lw=1.3)
    s.text(837, 134, "Manual Dual Emails", size=9.0, bold=True, color=SLATE_900, align="center")
    s.text(837, 148, "Draft & send 2 emails:", size=8.2, color=SLATE_600, align="center")
    s.text(837, 161, "1) Customer  2) Warehouse", size=8.1, bold=True, color=SLATE_700, align="center")

    # NO path (Exception)
    s.poly_arrow([(684, box_y + 75), (684, 224), (762, 224)], RED, lw=1.9)
    s.text(722, 217, "NO (ISSUE)", size=7.8, bold=True, color=RED, align="center")
    s.card(764, 194, 146, 62, fill=RED_BG, stroke=RED, r=8, lw=1.7)
    s.text(837, 211, "Manual Exception Loop", size=9.0, bold=True, color=RED_DARK, align="center")
    s.text(837, 226, "Email sales rep & wait", size=8.2, color=SLATE_700, align="center")
    s.text(837, 241, "-> Long multi-hour delays", size=8.1, bold=True, color=RED, align="center")

    # Loop-back arrow showing inbox backlog
    s.poly_arrow([(764, 244), (720, 244), (720, 276), (111, 276), (111, 232)], RED, lw=1.2, dash="4 3")
    s.pill(322, 267, 220, 18, "Re-enters shared inbox -> compounds backlog", RED_TINT, RED_DARK, size=7.8, stroke=RED_BORDER)

    # 3 Pain Point Cards
    pain_y = 310
    pain_h = 104
    pain_w = 286
    pains = [
        (
            "1. Slow, Fragile Manual Handoffs",
            "Every order requires toggling across Email, Salesforce, and Google Sheets. When exceptions occur or ops staff are in meetings or away, orders sit untouched in the shared inbox for hours.",
        ),
        (
            "2. High Risk of Human Error",
            "Re-keying SKUs, quantities, and customer IDs from PDFs introduces wrong shipments, oversold inventory, and missed updates - hurting customer trust and driving expensive manual rework.",
        ),
        (
            "3. Zero Scalability Under Growth",
            "Throughput scales linearly with headcount. Hardware order spikes overwhelm Operations, pulling skilled staff away from customer care, vendor coordination, and strategic improvements.",
        ),
    ]
    for i, (heading, body) in enumerate(pains):
        cx = 36 + i * (pain_w + 15)
        s.card(cx, pain_y, pain_w, pain_h, fill=RED_BG, stroke=RED_BORDER, r=9, left_bar=RED, left_bar_w=4.5)
        s.text(cx + 14, pain_y + 22, heading, size=10.5, bold=True, color=RED_DARK)
        s.wrapped_text(cx + 14, pain_y + 40, pain_w - 24, body, size=8.8, color=SLATE_700, line_h=12.6)

    # Bottom Metric Strip
    kpi_y = 428
    kpi_h = 68
    kpi_w = 212
    kpis = [
        ("2 - 6 Hours", "Typical Confirmation Wait (24h+ on Exceptions)"),
        ("5 Manual Steps", "Across 3 Disconnected Business Systems"),
        ("~5 - 8%", "Estimated Rework & Data-Entry Error Risk"),
        ("9 AM - 5 PM", "Constrained by Staff Availability & Leave"),
    ]
    for i, (val, lbl) in enumerate(kpis):
        kx = 36 + i * (kpi_w + 13.3)
        s.card(kx, kpi_y, kpi_w, kpi_h, fill=RED_BG, stroke=RED_BORDER, r=9)
        s.text(kx + 14, kpi_y + 28, val, size=16.5, bold=True, color=RED_DARK)
        s.wrapped_text(kx + 14, kpi_y + 44, kpi_w - 24, lbl, size=8.2, bold=True, color=SLATE_600, line_h=10.8)

    return s


def build_slide_2() -> SlidePage:
    """Slide 2: The Solution - Introducing OrderBot, Our Autonomous AI Agent."""
    s = SlidePage()
    s.fill_rect(0, 0, W, H, WHITE)
    s.header_and_footer(
        "SLIDE 2  -  PROPOSED AGENTIC AI SOLUTION",
        (0.05, 0.38, 0.28),
        (0.76, 1.0, 0.89),
        'The Solution: Introducing "OrderBot," Our Autonomous AI Agent',
        2,
    )

    # Automated Flowchart Panel
    s.card(36, 84, 888, 206, fill=SLATE_50, stroke=SLATE_200, r=10)
    s.circle(54, 99, 4, GREEN)
    s.text(
        64,
        103,
        "STREAMLINED END-TO-END ORDERBOT WORKFLOW  (GOAL: < 5 MINUTES  |  99.5% ACCURACY)",
        size=9.2,
        bold=True,
        color=SLATE_700,
    )

    # Trigger box
    s.card(50, 152, 114, 78, fill=WHITE, stroke=BLUE, r=9, lw=1.5, top_bar=BLUE_LIGHT, top_bar_h=20)
    s.text(107, 165.5, "TRIGGER (24/7)", size=7.8, bold=True, color=BLUE, align="center")
    s.text(107, 186, "PDF Order Arrives", size=9.0, bold=True, color=SLATE_900, align="center")
    s.text(107, 200, "Detected instantly", size=8.1, color=SLATE_600, align="center")
    s.text(107, 213, "via Email API", size=8.1, color=SLATE_600, align="center")

    s.poly_arrow([(164, 191), (192, 191)], BLUE, lw=1.8)

    # OrderBot Autonomous Hub
    s.card(194, 112, 304, 166, fill=BLUE_LIGHT, stroke=BLUE, r=11, lw=2.0, top_bar=NAVY, top_bar_h=25)
    s.text(346, 128.5, "ORDERBOT  -  AUTONOMOUS AI AGENT", size=9.2, bold=True, color=WHITE, align="center")

    # 3 Perception tools inside hub
    tools = [
        ("1. PDF Parsing Tool", "Extracts SKU, qty & customer", BLUE_BORDER, NAVY),
        ("2. Salesforce API", "Verifies account & credit status", BLUE_BORDER, CYAN_DARK),
        ("3. Google Sheets API", "Checks live inventory count", GREEN_BORDER, GREEN_DARK),
    ]
    for idx, (t_title, t_sub, t_stroke, t_col) in enumerate(tools):
        ty = 146 + idx * 42
        s.card(206, ty, 134, 34, fill=WHITE, stroke=t_stroke, r=6, lw=1.2)
        s.text(273, ty + 14, t_title, size=8.4, bold=True, color=t_col, align="center")
        s.text(273, ty + 26, t_sub, size=7.4, color=SLATE_600, align="center")

    # Arrows into Planning Engine
    s.poly_arrow([(340, 163), (366, 192)], BLUE, lw=1.3, head_size=5.2)
    s.poly_arrow([(340, 205), (366, 205)], BLUE, lw=1.3, head_size=5.2)
    s.poly_arrow([(340, 247), (366, 218)], BLUE, lw=1.3, head_size=5.2)

    # Planning & Decision Engine
    s.card(368, 150, 118, 114, fill=NAVY, stroke=MINT, r=8, lw=1.6)
    s.text(427, 170, "PLANNING &", size=8.6, bold=True, color=MINT, align="center")
    s.text(427, 182, "DECISION ENGINE", size=8.6, bold=True, color=MINT, align="center")
    s.text(427, 199, "Validates order,", size=7.8, color=SLATE_200, align="center")
    s.text(427, 211, "credit & stock;", size=7.8, color=SLATE_200, align="center")
    s.text(427, 223, "builds Success or", size=7.8, color=SLATE_200, align="center")
    s.text(427, 235, "Exception plan", size=7.8, color=SLATE_200, align="center")
    s.pill(377, 243, 100, 14, "+ Logs Memory", (0.08, 0.32, 0.28), (0.75, 1.0, 0.90), size=7.0)

    # Branch 1: ALL VALID (Green)
    s.poly_arrow([(498, 178), (532, 178), (532, 150), (562, 150)], GREEN, lw=2.0)
    s.pill(502, 128, 56, 15, "ALL VALID", GREEN_TINT, GREEN_DARK, size=7.2)

    s.card(564, 114, 164, 72, fill=GREEN_BG, stroke=GREEN, r=8, lw=1.6)
    s.text(646, 131, "Auto-Update Systems", size=9.0, bold=True, color=GREEN_DARK, align="center")
    s.text(576, 147, "* Update Salesforce order history", size=8.0, color=SLATE_700)
    s.text(576, 160, "* Decrement Google Sheets stock", size=8.0, color=SLATE_700)
    s.text(576, 173, "* Save full audit record", size=8.0, color=SLATE_700)

    s.poly_arrow([(728, 150), (750, 150)], GREEN, lw=1.9)

    s.card(752, 114, 158, 72, fill=GREEN, stroke=GREEN_DARK, r=8, lw=1.4)
    s.text(831, 132, "Instant Confirmation", size=9.3, bold=True, color=WHITE, align="center")
    s.text(764, 148, "* Emails customer receipt", size=8.1, color=GREEN_BG)
    s.text(764, 161, "* Dispatches warehouse pick", size=8.1, color=GREEN_BG)
    s.text(831, 176, "Completed in < 5 Min", size=8.0, bold=True, color=(0.75, 1.0, 0.90), align="center")

    # Branch 2: EXCEPTION (Amber + Human-in-the-Loop)
    s.poly_arrow([(498, 226), (532, 226), (532, 240), (562, 240)], AMBER, lw=2.0)
    s.pill(500, 248, 60, 15, "EXCEPTION", AMBER_TINT, AMBER_DARK, size=7.2)

    s.card(564, 200, 346, 78, fill=AMBER_BG, stroke=AMBER, r=8, lw=1.6)
    s.text(737, 217, "Smart Exception Handling + Human-in-the-Loop", size=9.2, bold=True, color=AMBER_DARK, align="center")
    s.text(578, 234, "* Emails sales rep immediately pinpointing exact missing fields or low stock", size=8.2, color=SLATE_700)
    s.text(578, 248, "* Flags high-value anomalies or repeat incomplete forms for Ops review", size=8.2, color=SLATE_700)
    s.text(737, 265, "Zero silent stalls  |  No unapproved actions on ambiguous orders", size=8.0, bold=True, color=AMBER_DARK, align="center")

    # Anatomy of OrderBot (5 Business-Friendly Pillars)
    s.circle(44, 308, 4, BLUE)
    s.text(54, 312, "HOW ORDERBOT WORKS IN PLAIN BUSINESS TERMS  (ANATOMY OF AN AGENT)", size=9.0, bold=True, color=SLATE_700)

    pillars = [
        ("1. Clear Goal", "Autonomously process new hardware orders from email receipt to fulfillment in under 5 minutes at 99.5% accuracy."),
        ("2. Perception", "Watches the shared inbox 24/7, reads PDF attachments, and queries live Salesforce accounts & Google Sheets stock."),
        ("3. Planning", "Breaks each order into steps and dynamically chooses between straight-through fulfillment or exception routing."),
        ("4. Action", "Updates Salesforce order history, decrements inventory in Sheets, and sends customer & warehouse emails."),
        ("5. Learning", "Logs every outcome to detect recurring patterns (e.g., repeat incomplete forms) and alert Ops proactively."),
    ]
    pw = 171.2
    py = 322
    ph = 114
    for i, (ptitle, pdesc) in enumerate(pillars):
        px = 36 + i * (pw + 8)
        s.card(px, py, pw, ph, fill=GREEN_BG, stroke=GREEN_BORDER, r=8, top_bar=GREEN, top_bar_h=4.0)
        s.text(px + 10, py + 21, ptitle, size=9.8, bold=True, color=GREEN_DARK)
        s.wrapped_text(px + 10, py + 37, pw - 18, pdesc, size=8.3, color=SLATE_700, line_h=12.0)

    # Bottom Benefits Ribbon
    ry = 448
    rh = 48
    rw = 212
    chips = [
        ("< 5 Min", "End-to-end order confirmation SLA"),
        ("99.5%", "Target straight-through accuracy"),
        ("24 / 7", "Always-on coverage, zero backlog"),
        ("100%", "Human oversight on all exceptions"),
    ]
    for i, (num, desc) in enumerate(chips):
        rx = 36 + i * (rw + 13.3)
        s.fill_rect(rx, ry, rw, rh, NAVY, r=8)
        s.text(rx + 14, ry + 29, num, size=14.0, bold=True, color=MINT)
        s.wrapped_text(rx + 78, ry + 20, rw - 88, desc, size=8.2, color=SLATE_200, line_h=11.0)

    return s


def build_slide_3() -> SlidePage:
    """Slide 3: The Business Impact & Recommended Low-Risk Next Steps."""
    s = SlidePage()
    s.fill_rect(0, 0, W, H, WHITE)
    s.header_and_footer(
        "SLIDE 3  -  BUSINESS VALUE & EXECUTION ROADMAP",
        (0.05, 0.30, 0.52),
        (0.76, 0.91, 1.0),
        "Business Impact & Recommended Low-Risk Next Steps",
        3,
    )

    # Section 1: Tangible Business Benefits
    s.circle(44, 94, 4, GREEN)
    s.text(54, 98, "EXPECTED TANGIBLE BUSINESS OUTCOMES", size=9.2, bold=True, color=SLATE_700)

    impacts = [
        ("Hours -> <5 Min", "95%+ Faster Fulfillment", "Customers receive instant order confirmation and warehouse dispatch starts immediately - even after hours."),
        ("99.5% Target", "Eliminated Manual Errors", "Structured PDF extraction and direct API updates remove copy-paste mistakes and stale stock counts."),
        ("15-20 Hrs / Wk", "Staff Time Reclaimed", "Frees Ops specialists from repetitive data entry to focus on strategic accounts, exceptions & SLA quality."),
        ("Scalable Growth", "Higher CSAT & Lower Cost", "Absorbs seasonal hardware order spikes without adding headcount while boosting customer satisfaction."),
    ]
    iw = 212
    iy = 108
    ih = 114
    for i, (metric, head, desc) in enumerate(impacts):
        ix = 36 + i * (iw + 13.3)
        s.card(ix, iy, iw, ih, fill=GREEN_BG, stroke=GREEN_BORDER, r=9, top_bar=GREEN, top_bar_h=4.5)
        s.text(ix + 12, iy + 29, metric, size=15.0, bold=True, color=GREEN_DARK)
        s.text(ix + 12, iy + 47, head, size=9.6, bold=True, color=SLATE_900)
        s.wrapped_text(ix + 12, iy + 62, iw - 22, desc, size=8.3, color=SLATE_600, line_h=11.8)

    # Section 2: Low-Risk 3-Phase Roadmap Panel
    s.card(36, 236, 888, 198, fill=SLATE_50, stroke=SLATE_200, r=10)
    s.circle(54, 253, 4, BLUE)
    s.text(
        64,
        257,
        'RECOMMENDED LOW-RISK IMPLEMENTATION ROADMAP  -  START WITH A "READ-ONLY" PROOF OF CONCEPT',
        size=9.2,
        bold=True,
        color=SLATE_700,
    )

    phases = [
        (
            320,
            "* RECOMMENDED NEXT STEP  |  WEEKS 1-3",
            BLUE,
            WHITE,
            'Phase 1: "Read-Only" Proof of Concept',
            BLUE_LIGHT,
            BLUE,
            2.0,
            [
                "Connect OrderBot to Email, Salesforce & Sheets in read-only shadow mode.",
                "Parses live PDFs & logs proposed actions without sending emails or editing data.",
                "Ops compares results side-by-side to prove >= 99.5% accuracy with zero risk.",
            ],
        ),
        (
            262,
            "PHASE 2  |  WEEKS 4-6",
            SLATE_200,
            SLATE_700,
            "Human-in-the-Loop Pilot",
            WHITE,
            SLATE_300,
            1.2,
            [
                "OrderBot drafts emails & system updates for 1-click Ops approval.",
                "Validate exception notifications with Sales & test safe fallback queues.",
                "Tune escalation rules for high-value or complex custom orders.",
            ],
        ),
        (
            262,
            "PHASE 3  |  WEEK 7+",
            GREEN_TINT,
            GREEN_DARK,
            "Controlled Autonomous Rollout",
            WHITE,
            GREEN_BORDER,
            1.3,
            [
                "Activate straight-through processing for standard verified orders.",
                "Keep mandatory human review on credit holds, low stock & low confidence.",
                "Track weekly SLA, accuracy & learning insights with Operations leadership.",
            ],
        ),
    ]

    cur_x = 50
    for pw, tag, tag_bg, tag_fg, ptitle, pfill, pstroke, plw, bullets in phases:
        s.card(cur_x, 268, pw, 152, fill=pfill, stroke=pstroke, r=9, lw=plw)
        s.pill(cur_x + 12, 279, min(pw - 24, len(tag) * 4.8 + 20), 17, tag, tag_bg, tag_fg, size=7.3)
        s.text(cur_x + 12, 314, ptitle, size=10.8, bold=True, color=NAVY)
        by = 332
        for b in bullets:
            s.text(cur_x + 12, by, "*", size=9.0, bold=True, color=BLUE if pstroke == BLUE else SLATE_700)
            by = s.wrapped_text(cur_x + 22, by, pw - 32, b, size=8.4, color=SLATE_700, line_h=11.6) + 5
        cur_x += pw + 12

    # Section 3: Governance & Decision Ask Bar
    s.fill_rect(36, 446, 888, 52, NAVY, r=9)
    gov_items = [
        ("GUARDRAIL 1", "Human-in-the-Loop:", "All ambiguous PDFs, credit holds & stock shortages route to Ops."),
        ("GUARDRAIL 2", "Safe Fallback:", "Any API outage pauses automation & alerts Ops - zero lost orders."),
        ("DECISION ASK", "Approve 3-Week PoC:", "Zero disruption, existing APIs, measurable Go/No-Go gate."),
    ]
    gw = 286
    for i, (badge, strong_lbl, desc) in enumerate(gov_items):
        gx = 48 + i * (gw + 8)
        s.pill(gx, 456, 74, 15, badge, (0.08, 0.34, 0.28), (0.72, 1.0, 0.88), size=7.0)
        s.text(gx + 80, 467, strong_lbl, size=8.6, bold=True, color=WHITE)
        s.wrapped_text(gx, 482, gw - 6, desc, size=7.9, color=SLATE_200, line_h=10.5)

    return s


def main() -> None:
    out_dir = os.path.dirname(os.path.abspath(__file__))
    ps_path = os.path.join(out_dir, "OrderBot_Automation_Proposal.ps")
    pdf_path = os.path.join(out_dir, "OrderBot_Automation_Proposal.pdf")

    slides = [build_slide_1(), build_slide_2(), build_slide_3()]
    ps_header = f"""%!PS-Adobe-3.0
%%Pages: {len(slides)}
%%BoundingBox: 0 0 {int(W)} {int(H)}
%%EndComments
<< /PageSize [{W:.1f} {H:.1f}] >> setpagedevice
"""
    ps_body = "".join(
        f"%%Page: {idx} {idx}\n" + slide.render()
        for idx, slide in enumerate(slides, start=1)
    )
    with open(ps_path, "w", encoding="ascii", errors="replace") as f:
        f.write(ps_header + ps_body + "%%EOF\n")

    subprocess.run(
        [
            "gs",
            "-q",
            "-dBATCH",
            "-dNOPAUSE",
            "-sDEVICE=pdfwrite",
            "-dPDFSETTINGS=/prepress",
            f"-sOutputFile={pdf_path}",
            ps_path,
        ],
        check=True,
    )
    os.remove(ps_path)
    print(f"Generated {pdf_path} ({os.path.getsize(pdf_path)} bytes)")


if __name__ == "__main__":
    main()
