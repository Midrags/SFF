# SteaMidra - Steam game setup and manifest tool (SFF)
# Copyright (c) 2025-2026 Midrag (https://github.com/Midrags)
#
# This file is part of SteaMidra.
#
# SteaMidra is free software: you can redistribute it and/or modify
# it under the terms of the GNU General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# SteaMidra is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
#
# You should have received a copy of the GNU General Public License
# along with SteaMidra.  If not, see <https://www.gnu.org/licenses/>.

_A = b'\x47\x53\xEF\x2A\x91\xBF\x33\xC5'
_B = b'\x6D\x08\xA7\x5E\xD4\x19\x7C\xF0'
_C = bytes([115,107,222,19,165,135,2,253,85,60,150,108,249,40,20,196,116,57,134,69,229,205,95,176,91,101,198,54,165,127,30,155,32,62,158,88,165,212,0,162,84,110,206,106,184,55,29,128,55,32,193,77,254,208,84,169,8,125,212,59,166,122,19,158,51,54,129,94,191,220,92,168])
_D = bytes([0,28,172,121,193,231,30,244,31,37,229,28,161,109,48,200,14,61,166,91,227,139,95,244,30,78,202,19,191,123,18,180,112,96,163])


def _r(d):
    k = _A + _B
    return bytes(b ^ k[i % len(k)] for i, b in enumerate(d)).decode()


def get_ci():
    return _r(_C)


def get_cs():
    return _r(_D)
