# -*- coding: utf-8 -*-
# Copyright (C) 2013 Jolla Ltd.
# Contact: Islam Amer <islam.amer@jollamobile.com>
# All rights reserved.
# 
# This program is free software; you can redistribute it and/or
# modify it under the terms of the GNU General Public License
# as published by the Free Software Foundation; either version 2
# of the License, or (at your option) any later version.
# 
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU General Public License for more details.
# 
# You should have received a copy of the GNU General Public License
# along with this program; if not, write to the Free Software
# Foundation, Inc., 51 Franklin Street, Fifth Floor, Boston, MA  02110-1301, USA.

import os, sys
from distutils.core import setup

from setuptools import find_packages

static_files = []

setup(
    name = "reports",
    version = "0.1.0",
    url = '',
    license = 'GPLv2',
    description = "Reports",
    author = 'Islam Amer <pharon@gmail.com>',
    packages = ['reports',
                'reports.repo',
                'reports.repo.templatetags',
                'reports.repo.migrations',
                'reports.jsonfield',
                ],    
    package_dir = {'':'src'},
    package_data = { 'reports.repo' : ['templates/*.html',
                                       'fixtures/*.yaml',
                                       'static/reports/css/images/*.png',
                                       'static/reports/css/*.css',
                                       'static/reports/js/*.js',
                                      ],
                    'reports' : ['templates/admin/*.html', ],
                   },
    data_files = static_files,
)
