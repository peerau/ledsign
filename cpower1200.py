#!/usr/bin/env python
"""
Driver for the C-Power 1200 
Copyright 2010-2012 Michael Farrell <http://micolous.id.au/>

Requires pyserial library in order to interface, and PIL to encode images.

Current windows binaries for PIL are available from here: http://www.lfd.uci.edu/~gohlke/pythonlibs/

This library is free software: you can redistribute it and/or modify
it under the terms of the GNU Lesser General Public License as published by
the Free Software Foundation, either version 3 of the License, or
(at your option) any later version.

This program is distributed in the hope that it will be useful,
but WITHOUT ANY WARRANTY; without even the implied warranty of
MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
GNU General Public License for more details.

You should have received a copy of the GNU Lesser General Public License
along with this program.  If not, see <http://www.gnu.org/licenses/>.
"""
import serial, string
from datetime import datetime, time
from struct import pack
from time import sleep
from warnings import warn
from cStringIO import StringIO
	

CC_DIVISION = 1
CC_TEXT = 2
CC_IMAGE = 3
CC_STATIC_TEXT = 4
CC_CLOCK = 5
CC_EXIT = 6
CC_SAVE = 7
CC_PLAY_SINGLE = 8
CC_PLAY_DOUBLE = 9
CC_SET_VARIABLE = 10
CC_PLAY_SET_VARIABLE = 11

EFFECT_NONE = 0
EFFECT_OPEN_LEFT = 1
EFFECT_OPEN_RIGHT = 2
EFFECT_OPEN_HORIZ = 3
EFFECT_OPEN_VERT = 4
EFFECT_SHUTTER = 5
EFFECT_MOVE_LEFT = 6
EFFECT_MOVE_RIGHT = 7
EFFECT_MOVE_UP = 8
EFFECT_MOVE_DOWN = 9
EFFECT_SCROLL_UP = 10
EFFECT_SCROLL_LEFT = 11
EFFECT_SCROLL_RIGHT = 12

ALIGN_LEFT = 0
ALIGN_CENTRE = ALIGN_CENTER = 1
ALIGN_RIGHT = 2

# colours
RED = 1
GREEN = 2
YELLOW = 3
BLUE = 4
PURPLE = 5
CYAN = 6
WHITE = 7

PACKET_TYPE = 0x68
CARD_TYPE = 0x32
PROTOCOL_CODE = 0x7B

IMAGE_GIF = 1
IMAGE_GIF_REF = 2
IMAGE_PKG_REF = 3
IMAGE_SIMPLE = 4

SAVE_SAVE = 0
SAVE_RESET = 1

class CPower1200(object):
	"""Implementation of the C-Power 1200 protocol"""
	
	def __init__(self, port):
		self.s = serial.Serial(port, 115200)
		self.file_id = None
		self.message_open = False
		print "opening %s" % self.s.portstr

	def _write(self, packet_data, unit_id=0xFF, confirmation=False):
		# start code    A5
		# packet type   68
		# card type     32
		# card ID       XX   or FF == all units
		# protocol code 7B
		# confirmation  00 / 01
		# packet length XX XX (uint16 le)
		# packet number XX (uint8)
		# total packets XX (uint8)
		# packet data
		# packet checksum (uint16 le)
		#     sum of each byte from "packet type" to "packet data" content
		
		if len(packet_data) > 0xFFFF:
			raise ValueError, 'Packet too long, packet fragmentation not yet implemented!'
			
		if not (0 <= unit_id <= 255):
			raise ValueError, 'Unit ID out of range (0 - 255)'
		
		confirmation = 0x01 if confirmation else 0x00
		body = pack('<BBBBBHBB', 
			PACKET_TYPE, CARD_TYPE, unit_id,
			PROTOCOL_CODE, confirmation, len(packet_data),
			0, # packet number
			0) # total packets - 1
		
		body += packet_data
		checksum = self.checksum(body)
		msg = self._escape_data(body + checksum)
		
		print '%r' % msg
		self.s.write("\xA5%s\xAE" % (msg,))
		
		# before another message can be sent, you need to wait a moment
		self.s.flush()
		sleep(1)
	
	def _escape_data(self, input):
		return input.replace('\xAA', '\xAA\x0A').replace('\xAE', '\xAA\0x0E').replace('\xA5', '\xAA\x05')
		
	def checksum(self, input):
		s = 0
		for c in input:
			s += ord(c)
		
		s &= 0xFFFF
		return pack('<H', s)
		
	def format_text(self, text='', colour=WHITE, size=0):
		"Generate formatted text"
		if not 0x00 < colour < 0x10:
			raise ValueError, "invalid colour"
		
		if not 0x00 <= size <= 0x0F:
			# TODO: Implement this as a transition from a pixel font size
			raise ValueError, "invalid size code"
		
		# colours appear to be as follows:
		#  bit 1: red
		#  bit 2: green (only on green-supporting sign)
		#  bit 3: blue  (only on full-colour sign)
		
		# the "colour / size" code has the high 4 bits as the colour,
		# and the low 4 bits as the size.
		colour_size = chr( (colour << 4) ^ size )
		
		o = ''
		for c in text.encode('ascii'):
			o += colour_size + '\0' + c
		
		return o
		
	def send_text(self, window, formatted_text, effect=EFFECT_SCROLL_LEFT, alignment=ALIGN_LEFT, speed=30, stay_time=2):
		if not 0 <= window <= 7:
			raise ValueError, "invalid window (must be 0 - 7)"
		
		packet = pack('<BBBBBH', CC_TEXT, window, effect, alignment, speed, stay_time) + formatted_text
		
		self._write(packet)
	
	def send_static_text(self, window, text, x=0, y=0, width=64, height=16, speed=30, stay_time=2, alignment=ALIGN_LEFT, font_size=1, red=0, green=0, blue=0):
		if not 0 <= window <= 7:
			raise ValueError, "invalid window (must be 0 - 7)"
			
		packet = pack('<BBBBHHHHBBBB',
			CC_STATIC_TEXT, window,
			1, # simple text data
			alignment, x, y, width, height,
			font_size, red, green, blue) + text + '\0'
		
		# TODO: fix this.
		s._write(packet)
			
			
			
	
	def send_window(self, window, x, y, width, height):
		# TODO: protocol supports sending multiple window definition at once.
		# Make a way to expose this in the API.
		
		
		
		if not 0 <= window <= 7:
			raise ValueError, "invalid window (must be 0 - 7)"
		
		# This call is 1-indexed window ID rather than 0-indexed.
		window += 1
		
		packet = pack('<BBHHHH', CC_DIVISION, window, x, y, width, height)
		
		self._write(packet)
	
	def send_image(self, window, image, speed=30, stay_time=2, x=0, y=0):
		"Sends an image to the sign.  Should be a PIL Image object."
		if not 0 <= window <= 7:
			raise ValueError, "invalid window (must be 0 - 7)"
			
		ibuf = StringIO()
		image.convert('I')
		
		# image.save accepts a file-like object. (undocumented)
		image.save(ibuf, 'gif')
		
		packet = pack('<BBBBHBHH',
			CC_IMAGE, window, 
			0, # mode 0 == draw
			speed, stay_time, IMAGE_GIF,
			x, y) + ibuf.getvalue()
		
		# FIXME: doesn't work.
		self._write(packet)
			
		
	
	#def show_clock
	def save(self):
		packet = pack('<BBH', CC_SAVE, SAVE_SAVE, 0)
		self._write(packet)
	
	def reset(self):
		packet = pack('<BBH', CC_SAVE, SAVE_RESET, 0)
		self._write(packet)
	
	def exit_show(self):
		packet = pack('<B', CC_EXIT)
		self._write(packet)
		
	def close(self):
		self.s.close()

if __name__ == '__main__':
	from sys import argv
	import Image
	
	s = CPower1200(argv[1])
	#s.reset()
	s.exit_show()
	
	#s.send_window(1, 0, 8, 64, 8)
	txt = s.format_text('Hello', RED, 0) + s.format_text(' World!', GREEN, 0)
	s.send_text(0, txt, EFFECT_NONE)
	#s.send_static_text(0, 'Hello World!')
	#img = Image.open('test.png')
	#s.send_image(0, img)
	
	s.save()
	
	
