all: install 

install:
	python setup.py install --root=$(DESTDIR) --prefix=$(PREFIX)
	install -D -m 644 conf/supervisor/reports.conf    $(DESTDIR)/etc/supervisor/conf.d/reports.conf

clean:
	python setup.py clean
