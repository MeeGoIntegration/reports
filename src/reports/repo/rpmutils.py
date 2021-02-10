# -*- coding: utf-8 -*-
import re
from collections import namedtuple
from itertools import izip_longest

_EMPTY = (None, '')
_NOT_SEGMET = re.compile('^[^A-Za-z0-9~^]+')
_SEGMENT = re.compile(r'^(~|[\^]|[0-9]+|[A-Za-z]+)')


def rpmvercmp(a, b):
    """Compare rpm version or release strings

    Test cases from

    https://github.com/rpm-software-management/rpm/blob/c7e711bba58374f03347c795a567441cbef3de58/tests/rpmvercmp.at

    >>> rpmvercmp('1.0', '1.0')
    0
    >>> rpmvercmp('1.0', '2.0')
    -1
    >>> rpmvercmp('2.0', '1.0')
    1

    >>> rpmvercmp('2.0.1', '2.0.1')
    0
    >>> rpmvercmp('2.0', '2.0.1')
    -1
    >>> rpmvercmp('2.0.1', '2.0')
    1

    >>> rpmvercmp('2.0.1a', '2.0.1a')
    0
    >>> rpmvercmp('2.0.1a', '2.0.1')
    1
    >>> rpmvercmp('2.0.1', '2.0.1a')
    -1

    >>> rpmvercmp('5.5p1', '5.5p1')
    0
    >>> rpmvercmp('5.5p1', '5.5p2')
    -1
    >>> rpmvercmp('5.5p2', '5.5p1')
    1

    >>> rpmvercmp('5.5p10', '5.5p10')
    0
    >>> rpmvercmp('5.5p1', '5.5p10')
    -1
    >>> rpmvercmp('5.5p10', '5.5p1')
    1

    >>> rpmvercmp('10xyz', '10.1xyz')
    -1
    >>> rpmvercmp('10.1xyz', '10xyz')
    1

    >>> rpmvercmp('xyz10', 'xyz10')
    0
    >>> rpmvercmp('xyz10', 'xyz10.1')
    -1
    >>> rpmvercmp('xyz10.1', 'xyz10')
    1

    >>> rpmvercmp('xyz.4', 'xyz.4')
    0
    >>> rpmvercmp('xyz.4', '8')
    -1
    >>> rpmvercmp('8', 'xyz.4')
    1
    >>> rpmvercmp('xyz.4', '2')
    -1
    >>> rpmvercmp('2', 'xyz.4')
    1

    >>> rpmvercmp('5.5p2', '5.6p1')
    -1
    >>> rpmvercmp('5.6p1', '5.5p2')
    1

    >>> rpmvercmp('5.6p1', '6.5p1')
    -1
    >>> rpmvercmp('6.5p1', '5.6p1')
    1

    >>> rpmvercmp('6.0.rc1', '6.0')
    1
    >>> rpmvercmp('6.0', '6.0.rc1')
    -1

    >>> rpmvercmp('10b2', '10a1')
    1
    >>> rpmvercmp('10a2', '10b2')
    -1

    >>> rpmvercmp('1.0aa', '1.0aa')
    0
    >>> rpmvercmp('1.0a', '1.0aa')
    -1
    >>> rpmvercmp('1.0aa', '1.0a')
    1

    >>> rpmvercmp('10.0001', '10.0001')
    0
    >>> rpmvercmp('10.0001', '10.1')
    0
    >>> rpmvercmp('10.1', '10.0001')
    0
    >>> rpmvercmp('10.0001', '10.0039')
    -1
    >>> rpmvercmp('10.0039', '10.0001')
    1

    >>> rpmvercmp('4.999.9', '5.0')
    -1
    >>> rpmvercmp('5.0', '4.999.9')
    1

    >>> rpmvercmp('20101121', '20101121')
    0
    >>> rpmvercmp('20101121', '20101122')
    -1
    >>> rpmvercmp('20101122', '20101121')
    1

    >>> rpmvercmp('2_0', '2_0')
    0
    >>> rpmvercmp('2.0', '2_0')
    0
    >>> rpmvercmp('2_0', '2.0')
    0

    # RhBug:178798 case
    >>> rpmvercmp('a', 'a')
    0
    >>> rpmvercmp('a+', 'a+')
    0
    >>> rpmvercmp('a+', 'a_')
    0
    >>> rpmvercmp('a_', 'a+')
    0
    >>> rpmvercmp('+a', '+a')
    0
    >>> rpmvercmp('+a', '_a')
    0
    >>> rpmvercmp('_a', '+a')
    0
    >>> rpmvercmp('+_', '+_')
    0
    >>> rpmvercmp('_+', '+_')
    0
    >>> rpmvercmp('_+', '_+')
    0
    >>> rpmvercmp('+', '_')
    0
    >>> rpmvercmp('_', '+')
    0

    # Basic testcases for tilde sorting
    >>> rpmvercmp('1.0~rc1', '1.0~rc1')
    0
    >>> rpmvercmp('1.0~rc1', '1.0')
    -1
    >>> rpmvercmp('1.0', '1.0~rc1')
    1
    >>> rpmvercmp('1.0~rc1', '1.0~rc2')
    -1
    >>> rpmvercmp('1.0~rc2', '1.0~rc1')
    1
    >>> rpmvercmp('1.0~rc1~git123', '1.0~rc1~git123')
    0
    >>> rpmvercmp('1.0~rc1~git123', '1.0~rc1')
    -1
    >>> rpmvercmp('1.0~rc1', '1.0~rc1~git123')
    1

    # Basic testcases for caret sorting
    >>> rpmvercmp('1.0^', '1.0^')
    0
    >>> rpmvercmp('1.0^', '1.0')
    1
    >>> rpmvercmp('1.0', '1.0^')
    -1
    >>> rpmvercmp('1.0^git1', '1.0^git1')
    0
    >>> rpmvercmp('1.0^git1', '1.0')
    1
    >>> rpmvercmp('1.0', '1.0^git1')
    -1
    >>> rpmvercmp('1.0^git1', '1.0^git2')
    -1
    >>> rpmvercmp('1.0^git2', '1.0^git1')
    1
    >>> rpmvercmp('1.0^git1', '1.01')
    -1
    >>> rpmvercmp('1.01', '1.0^git1')
    1
    >>> rpmvercmp('1.0^20160101', '1.0^20160101')
    0
    >>> rpmvercmp('1.0^20160101', '1.0.1')
    -1
    >>> rpmvercmp('1.0.1', '1.0^20160101')
    1
    >>> rpmvercmp('1.0^20160101^git1', '1.0^20160101^git1')
    0
    >>> rpmvercmp('1.0^20160102', '1.0^20160101^git1')
    1
    >>> rpmvercmp('1.0^20160101^git1', '1.0^20160102')
    -1

    # Basic testcases for tilde and caret sorting
    >>> rpmvercmp('1.0~rc1^git1', '1.0~rc1^git1')
    0
    >>> rpmvercmp('1.0~rc1^git1', '1.0~rc1')
    1
    >>> rpmvercmp('1.0~rc1', '1.0~rc1^git1')
    -1
    >>> rpmvercmp('1.0^git1~pre', '1.0^git1~pre')
    0
    >>> rpmvercmp('1.0^git1', '1.0^git1~pre')
    1
    >>> rpmvercmp('1.0^git1~pre', '1.0^git1')
    -1

    # These are included here to document current, arguably buggy behaviors
    # for reference purposes and for easy checking against  unintended
    # behavior changes.

    # RPM version comparison oddities
    # RhBug:811992 case
    >>> rpmvercmp('1b.fc17', '1b.fc17')
    0
    >>> rpmvercmp('1b.fc17', '1.fc17')
    -1
    >>> rpmvercmp('1.fc17', '1b.fc17')
    1
    >>> rpmvercmp('1g.fc17', '1g.fc17')
    0
    >>> rpmvercmp('1g.fc17', '1.fc17')
    1
    >>> rpmvercmp('1.fc17', '1g.fc17')
    -1

    # Non-ascii characters are considered equal so these are all the same, eh..
    >>> rpmvercmp('1.1.α', '1.1.α')
    0
    >>> rpmvercmp('1.1.α', '1.1.β')
    0
    >>> rpmvercmp('1.1.β', '1.1.α')
    0
    >>> rpmvercmp('1.1.αα', '1.1.α')
    0
    >>> rpmvercmp('1.1.α', '1.1.ββ')
    0
    >>> rpmvercmp('1.1.ββ', '1.1.αα')
    0
    """
    if a in _EMPTY:
        if b not in _EMPTY:
            return -1
    elif b in _EMPTY:
        return 1

    if a == b:
        return 0

    for seg_a, seg_b in izip_longest(_segments(a), _segments(b)):
        if seg_a == '~':
            if seg_b != '~':
                return -1
        elif seg_b == '~':
            return 1

        if seg_a is None:
            if seg_b is None:
                return 0
            else:
                return -1
        elif seg_b is None:
            return 1

        try:
            seg_a = int(seg_a)
            adigit = True
        except ValueError:
            adigit = False
        try:
            seg_b = int(seg_b)
            bdigit = True
        except ValueError:
            bdigit = False

        if adigit:
            if not bdigit:
                return 1
        elif bdigit:
            return -1

        result = cmp(seg_a, seg_b)
        if result != 0:
            return result
    return 0


def _segments(label):
    while label:
        label = _NOT_SEGMET.sub('', label)
        sm = _SEGMENT.match(label)
        if sm:
            yield sm.group()
            label = label[sm.end():]


def evrcmp(a, b, ignore_release=False):
    """Compare EVRs

    Takes either EVRs, tuples, or strings in format accepted by
    EVR.from_string()

    >>> evrcmp('1', '1')
    0
    >>> evrcmp('2', '1')
    1
    >>> evrcmp('1', '2')
    -1

    >>> evrcmp('1-1', '1-1')
    0
    >>> evrcmp('1-2', '1-1')
    1
    >>> evrcmp('1-1', '1-2')
    -1

    >>> evrcmp('2-1', '1-1')
    1
    >>> evrcmp('1-1', '2-1')
    -1

    >>> evrcmp('1:1', '1')
    1
    >>> evrcmp('1:1', '2')
    1
    >>> evrcmp('1:2', '2:1')
    -1

    >>> evrcmp('1-1-1', '1-1-2')
    -1
    """
    if not isinstance(a, EVR):
        if isinstance(a, basestring):
            a = EVR.from_string(a)
        else:
            a = EVR(*a)
    if not isinstance(b, EVR):
        if isinstance(b, basestring):
            b = EVR.from_string(b)
        else:
            b = EVR(*b)

    epoch_result = cmp(a.epoch, b.epoch)
    if epoch_result:
        return epoch_result

    ver_result = rpmvercmp(a.ver, b.ver)
    if ignore_release or ver_result:
        return ver_result

    return rpmvercmp(a.rel, b.rel)


class EVR(namedtuple('EVR', ['epoch', 'ver', 'rel'])):
    __slots__ = ()

    def __new__(cls, *parts):
        """
        >>> EVR('1', 2, 3)
        EVR(epoch=1, ver='2', rel='3')
        >>> EVR('foo', '2', '3')
        Traceback (most recent call last):
            ...
        ValueError: Non numeric epoch 'foo'
        >>> EVR(1, 2, 3, 4)
        Traceback (most recent call last):
            ...
        ValueError: EVR requires 3 parts, got (1, 2, 3, 4)
        """
        if len(parts) != 3:
            raise ValueError("EVR requires 3 parts, got %s" % str(parts))
        epoch, ver, rel = parts
        if epoch is None:
            epoch = 0
        elif not isinstance(epoch, int):
            try:
                epoch = int(epoch)
            except ValueError:
                raise ValueError("Non numeric epoch '%s'" % epoch)
        if ver is None:
            ver = ''
        elif not isinstance(ver, basestring):
            ver = str(ver)
        if rel is None:
            rel = ''
        elif not isinstance(rel, basestring):
            rel = str(rel)
        return super(EVR, cls).__new__(cls, epoch, ver, rel)

    def __lt__(self, other):
        """
        >>> EVR(1,1,1) < EVR(1,1,0)
        False
        >>> EVR(1,1,1) < EVR(1,1,1)
        False
        >>> EVR(1,1,1) < EVR(1,1,2)
        True
        """
        return evrcmp(self, other) < 0

    def __le__(self, other):
        """
        >>> EVR(1,1,1) <= EVR(1,1,0)
        False
        >>> EVR(1,1,1) <= EVR(1,1,1)
        True
        >>> EVR(1,1,1) <= EVR(1,1,2)
        True
        """
        return evrcmp(self, other) <= 0

    def __gt__(self, other):
        """
        >>> EVR(1,1,1) > EVR(1,1,0)
        True
        >>> EVR(1,1,1) > EVR(1,1,1)
        False
        >>> EVR(1,1,1) > EVR(1,1,2)
        False
        """
        return evrcmp(self, other) > 0

    def __ge__(self, other):
        """
        >>> EVR(1,1,1) >= EVR(1,1,0)
        True
        >>> EVR(1,1,1) >= EVR(1,1,1)
        True
        >>> EVR(1,1,1) >= EVR(1,1,2)
        False
        """
        return evrcmp(self, other) >= 0

    def __eq__(self, other):
        """
        >>> EVR(1,1,1) == EVR(1,1,1)
        True
        >>> EVR(1,1,1) == EVR(1,1,2)
        False
        """
        return evrcmp(self, other) == 0

    def __ne__(self, other):
        """
        >>> EVR(1,1,1) != EVR(1,1,1)
        False
        >>> EVR(1,1,1) != EVR(1,1,2)
        True
        """
        return evrcmp(self, other) != 0

    def __cmp__(self, other):
        return evrcmp(self, other)

    def __str__(self):
        """
        >>> str(EVR(1,2,3))
        '1:2-3'
        >>> str(EVR.from_string('1'))
        '1'
        >>> str(EVR.from_string('1-2'))
        '1-2'
        >>> str(EVR.from_string('1:2'))
        '1:2'
        """
        if self.epoch:
            evr = "%s:%s" % (self.epoch, self.ver)
        else:
            evr = self.ver
        if self.rel:
            evr = '%s-%s' % (evr, self.rel)
        return evr

    @classmethod
    def from_string(cls, evrstring):
        """Converts string to EVR tuple.

        Accepts string in format
            [<epoch>:]<version>[-<release>]

        >>> EVR.from_string('1:2-3')
        EVR(epoch=1, ver='2', rel='3')
        >>> EVR.from_string('1-2')
        EVR(epoch=0, ver='1', rel='2')
        >>> EVR.from_string('1')
        EVR(epoch=0, ver='1', rel='')
        """
        if not isinstance(evrstring, basestring):
            raise TypeError("Requires str, not %s" % type(evrstring))

        parts = evrstring.split(':', 1)
        if len(parts) == 2:
            epoch = parts[0]
        else:
            epoch = 0
        parts = parts[-1].split('-', 1)
        if len(parts) == 2:
            ver, rel = parts
        else:
            ver = parts[0]
            rel = ''
        return cls(epoch, ver, rel)


def split_rpm_filename(filename):
    """Split standard style rpm filename into components

    Returns: tuple(name, version, release, epoch, arch)

    >>> split_rpm_filename('foo-1.0-1.i386.rpm')
    ('foo', '1.0', '1', '', 'i386')
    >>> split_rpm_filename('1:bar-9-123a.ia64.rpm')
    ('bar', '9', '123a', '1', 'ia64')
    """

    if filename[-4:] == '.rpm':
        name = filename[:-4]
    else:
        name = filename

    name, arch = name.rsplit('.', 1)
    name, rel = name.rsplit('-', 1)
    name, ver = name.rsplit('-', 1)
    if ':' in name:
        epoch, name = name.split(':', 1)
    else:
        epoch = ''

    return name, ver, rel, epoch, arch
