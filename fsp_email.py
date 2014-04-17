#!/usr/bin/python

from email.parser import Parser
import email.utils
from email.mime.text import MIMEText
import email.mime.multipart
import email.mime.message
from BeautifulSoup import BeautifulSoup
import re
import os
import datetime
import pytz
import subprocess
import fsp_reservation

_RE_crew1 = re.compile("^\s*Pilot: (.+?)\s*$")
_RE_crew2 = re.compile("^\s*Instructor: (.+?)\s*$")
_RE_crew3 = re.compile("^\s*For: (.+?)\s*$")
_RE_aircraft = re.compile("^\s*Aircraft: .*?(\S+)\s*$")
_RE_start = re.compile("^\s*Resource Start Time: (\d+)/(\d+)/(\d+) (\d+):(\d+) ([AP])M\s*$")
_RE_end = re.compile("^\s*Resource End Time: (\d+)/(\d+)/(\d+) (\d+):(\d+) ([AP])M\s*$")
_RE_resv_id = re.compile("^\s*Reservation Id: (\d+)\s*$")

class UnusableEmail(Exception):
    pass

class FSPConnectorConfig(object):
    def __init__(self, mailbox_name):
        self.mailbox_name = mailbox_name
        self.tz = None
        self.user = None
        self.url = None
        self.password = None
        missing = set(('timezone', 'user'))
        with open(os.path.join(os.path.expanduser("~/fsp_config"), mailbox_name)) as f:
            for line in f:
                if line.startswith('#'):
                    continue
                if line.endswith("\n"):
                    line = line[:-1]
                if line.endswith("\r"):
                    line = line[:-1]
                directive, argument = line.split(None, 1)
                if directive == 'timezone':
                    self.tz = pytz.timezone(argument)
                elif directive == 'user':
                    self.user = argument
                elif directive == 'url':
                    self.url = argument
                else:
                    raise ValueError("Unknown directive %s in config file" % (directive,))
                if directive in missing:
                    missing.remove(directive)
        if missing:
            raise ValueError("Missing directives in config file: %r" % (missing,))
        with open(os.path.join(os.path.expanduser("~/.fsp_password"), mailbox_name)) as f:
            for line in f:
                if line.endswith("\n"):
                    line = line[:-1]
                if line.endswith("\r"):
                    line = line[:-1]
                self.password = line
                break
        if self.password is None:
            raise ValueError("Missing Wi-Flight API password")

def parse_date(tz, m):
    """Given a regex match object that matched the
    date and time format used by Flight Schedule Pro,
    return a datetime object"""
    h = int(m.group(4))
    if m.group(6) == 'P':
        h += 12
    try:
        local = datetime.datetime(
            int(m.group(3)),
            int(m.group(2)), int(m.group(1)),
            h, int(m.group(5))
        )
    except ValueError:
        raise UnusableEmail("Unparseable date&time " + m.group(0).strip())
    try:
        z = tz.localize(local, is_dst=None).astimezone(pytz.utc)
    except pytz.exceptions.InvalidTimeError, e:
        raise UnusableEmail("Unable to convert %s to UTC: %r" % (local, e))
    return z.replace(tzinfo=None)

def process_message(config, msg):
    crew = []
    start = None
    end = None
    tail = None
    reservation_id = None

    display, sender = email.utils.parseaddr(msg['From'])
    if sender != 'notify@flightschedulepro.com':
        raise UnusableEmail("Email does not come from notify@flightschedulepro.com")
    if msg.get_content_type() != 'text/html':
        raise UnusableEmail("Email was expected to be in HTML format but is not")
    try:
        top = BeautifulSoup(msg.get_payload())
    except Exception, e:
        raise UnusableEmail("HTML parsing failed: " + str(e))
    if not top.body:
        raise UnusableEmail("HTML message has no body!")
    table = top.body.find('table', attrs={'class' : 'TableBodys'})
    if not table:
        raise UnusableEmail("Cannot find the data (\"TableBodys\") in the message")
    td = table.find('td', attrs={'class' : 'TextStandard'})
    if not td:
        raise UnusableEmail("Cannot find the data (\"TextStandard\") in the message")
    isdelete = False
    for thing in td:
        if isinstance(thing, basestring):
            if 'following reservation has been deleted' in thing:
                isdelete = True
            elif 'are the current reservation details' in thing:
                # This means an edited reservation. Everything that precedes
                # pertains to the old contents of the reservation, so wipe
                # it out.
                crew = []
                start = None
                end = None
                tail = None
            else:
                m = re.match(_RE_crew1, thing)
                if m:
                    crew.append(m.group(1))
                    continue
                m = re.match(_RE_crew2, thing)
                if m:
                    crew.append(m.group(1))
                    continue
                m = re.match(_RE_crew3, thing)
                if m:
                    crew.append(m.group(1))
                    continue
                m = re.match(_RE_aircraft, thing)
                if m:
                    tail = m.group(1)
                    continue
                m = re.match(_RE_start, thing)
                if m:
                    start = parse_date(config.tz, m)
                    continue
                m = re.match(_RE_end, thing)
                if m:
                    end = parse_date(config.tz, m)
                    continue
                m = re.match(_RE_resv_id, thing)
                if m:
                    reservation_id = int(m.group(1))
                    continue
    r = fsp_reservation.Reservation(
        crew=set(crew), start=start, end=end,
        tail=tail, reservation_id=reservation_id
    )
    fsp_reservation.process_reservation_notice(config, r, UnusableEmail, isdelete)

def process_file(mailbox_name, f):
    config = FSPConnectorConfig(mailbox_name)
    msg = None
    try:
        msg = Parser().parse(f)
        process_message(config, msg)
    except UnusableEmail, e:
        body = "An email was received at " + mailbox_name + \
            "@fspnotify.wi-flight.net\n" + \
            "but the Flight Schedule Pro reservations email parser was not able\n" + \
            "to understand it. There will be no retry. The reason was:\n\n" + \
            e.message + "\n"
        errormsg = MIMEText(body, 'plain', 'us-ascii')
        if msg:
            mainmsg = email.mime.multipart.MIMEMultipart('mixed')
            mainmsg.attach(errormsg)
            mainmsg.attach(email.mime.message.MIMEMessage(msg))
        else:
            mainmsg = errormsg
        mainmsg['Subject'] = "FSP email failure"
        mainmsg['From'] = "Flight Schedule Pro connector <Postmaster@wi-flight.net>"
        if 'LOGNAME' in os.environ:
            mainmsg['To'] = os.environ['LOGNAME']
        elif 'USER' in os.environ:
            mainmsg['To'] = os.environ['USER']
        else:
            mainmsg['To'] = 'root'
        mainmsg['X-Mailer'] = 'GASN Flight Schedule Pro connector'

        sendmail = subprocess.Popen(
            ('/usr/lib/sendmail', '-t'),
            stdin=subprocess.PIPE,
            close_fds=True
        )
        f = sendmail.stdin
        f.write(mainmsg.as_string())
        f.close()
        sendmail.wait()
