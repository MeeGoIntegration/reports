# -*- coding: utf-8 -*-
from django import db
from django.db import models, migrations


class Migration(migrations.Migration):

    def forwards(self, orm):
        # Adding model 'Arch'
        db.create_table('repo_arch', (
            ('id', self.gf('django.db.models.fields.AutoField')(primary_key=True)),
            ('name', self.gf('django.db.models.fields.CharField')(unique=True, max_length=50)),
        ))
        db.send_create_signal('repo', ['Arch'])

        # Adding model 'DocService'
        db.create_table('repo_docservice', (
            ('id', self.gf('django.db.models.fields.AutoField')(primary_key=True)),
            ('name', self.gf('django.db.models.fields.CharField')(unique=True, max_length=250)),
            ('weburl', self.gf('django.db.models.fields.CharField')(max_length=250, null=True, blank=True)),
        ))
        db.send_create_signal('repo', ['DocService'])

        # Adding model 'LocalizationService'
        db.create_table('repo_localizationservice', (
            ('id', self.gf('django.db.models.fields.AutoField')(primary_key=True)),
            ('name', self.gf('django.db.models.fields.CharField')(unique=True, max_length=250)),
            ('apiurl', self.gf('django.db.models.fields.CharField')(max_length=250, null=True, blank=True)),
            ('weburl', self.gf('django.db.models.fields.CharField')(max_length=250, null=True, blank=True)),
        ))
        db.send_create_signal('repo', ['LocalizationService'])

        # Adding model 'BuildService'
        db.create_table('repo_buildservice', (
            ('id', self.gf('django.db.models.fields.AutoField')(primary_key=True)),
            ('name', self.gf('django.db.models.fields.CharField')(unique=True, max_length=250)),
            ('namespace', self.gf('django.db.models.fields.CharField')(unique=True, max_length=50)),
            ('apiurl', self.gf('django.db.models.fields.CharField')(unique=True, max_length=250)),
            ('weburl', self.gf('django.db.models.fields.CharField')(max_length=250, null=True, blank=True)),
        ))
        db.send_create_signal('repo', ['BuildService'])

        # Adding model 'Project'
        db.create_table('repo_project', (
            ('id', self.gf('django.db.models.fields.AutoField')(primary_key=True)),
            ('name', self.gf('django.db.models.fields.CharField')(max_length=100)),
            ('buildservice', self.gf('django.db.models.fields.related.ForeignKey')(to=orm['repo.BuildService'], null=True)),
            ('request_target', self.gf('django.db.models.fields.related.ForeignKey')(blank=True, related_name='request_source', null=True, to=orm['repo.Project'])),
        ))
        db.send_create_signal('repo', ['Project'])

        # Adding model 'Platform'
        db.create_table('repo_platform', (
            ('id', self.gf('django.db.models.fields.AutoField')(primary_key=True)),
            ('name', self.gf('django.db.models.fields.CharField')(unique=True, max_length=100)),
        ))
        db.send_create_signal('repo', ['Platform'])

        # Adding model 'RepoServer'
        db.create_table('repo_reposerver', (
            ('id', self.gf('django.db.models.fields.AutoField')(primary_key=True)),
            ('url', self.gf('django.db.models.fields.CharField')(unique=True, max_length=250)),
            ('buildservice', self.gf('django.db.models.fields.related.ForeignKey')(to=orm['repo.BuildService'], null=True, blank=True)),
        ))
        db.send_create_signal('repo', ['RepoServer'])

        # Adding model 'Repo'
        db.create_table('repo_repo', (
            ('id', self.gf('django.db.models.fields.AutoField')(primary_key=True)),
            ('server', self.gf('django.db.models.fields.related.ForeignKey')(to=orm['repo.RepoServer'])),
            ('repo_path', self.gf('django.db.models.fields.CharField')(max_length=250)),
            ('platform', self.gf('django.db.models.fields.related.ForeignKey')(to=orm['repo.Platform'])),
            ('release', self.gf('django.db.models.fields.CharField')(max_length=250)),
            ('release_date', self.gf('django.db.models.fields.DateField')(null=True, blank=True)),
        ))
        db.send_create_signal('repo', ['Repo'])

        # Adding unique constraint on 'Repo', fields ['server', 'repo_path']
        db.create_unique('repo_repo', ['server_id', 'repo_path'])

        # Adding M2M table for field projects on 'Repo'
        m2m_table_name = db.shorten_name('repo_repo_projects')
        db.create_table(m2m_table_name, (
            ('id', models.AutoField(verbose_name='ID', primary_key=True, auto_created=True)),
            ('repo', models.ForeignKey(orm['repo.repo'], null=False)),
            ('project', models.ForeignKey(orm['repo.project'], null=False))
        ))
        db.create_unique(m2m_table_name, ['repo_id', 'project_id'])

        # Adding M2M table for field components on 'Repo'
        m2m_table_name = db.shorten_name('repo_repo_components')
        db.create_table(m2m_table_name, (
            ('id', models.AutoField(verbose_name='ID', primary_key=True, auto_created=True)),
            ('from_repo', models.ForeignKey(orm['repo.repo'], null=False)),
            ('to_repo', models.ForeignKey(orm['repo.repo'], null=False))
        ))
        db.create_unique(m2m_table_name, ['from_repo_id', 'to_repo_id'])

        # Adding M2M table for field archs on 'Repo'
        m2m_table_name = db.shorten_name('repo_repo_archs')
        db.create_table(m2m_table_name, (
            ('id', models.AutoField(verbose_name='ID', primary_key=True, auto_created=True)),
            ('repo', models.ForeignKey(orm['repo.repo'], null=False)),
            ('arch', models.ForeignKey(orm['repo.arch'], null=False))
        ))
        db.create_unique(m2m_table_name, ['repo_id', 'arch_id'])

        # Adding model 'Note'
        db.create_table('repo_note', (
            ('id', self.gf('django.db.models.fields.AutoField')(primary_key=True)),
            ('body', self.gf('django.db.models.fields.TextField')()),
            ('repo', self.gf('django.db.models.fields.related.ForeignKey')(to=orm['repo.Repo'], unique=True)),
        ))
        db.send_create_signal('repo', ['Note'])

        # Adding model 'IssueTracker'
        db.create_table('repo_issuetracker', (
            ('id', self.gf('django.db.models.fields.AutoField')(primary_key=True)),
            ('name', self.gf('django.db.models.fields.CharField')(unique=True, max_length=100)),
            ('re', self.gf('django.db.models.fields.CharField')(max_length=100)),
            ('url', self.gf('django.db.models.fields.CharField')(max_length=200)),
        ))
        db.send_create_signal('repo', ['IssueTracker'])

        # Adding M2M table for field platform on 'IssueTracker'
        m2m_table_name = db.shorten_name('repo_issuetracker_platform')
        db.create_table(m2m_table_name, (
            ('id', models.AutoField(verbose_name='ID', primary_key=True, auto_created=True)),
            ('issuetracker', models.ForeignKey(orm['repo.issuetracker'], null=False)),
            ('platform', models.ForeignKey(orm['repo.platform'], null=False))
        ))
        db.create_unique(m2m_table_name, ['issuetracker_id', 'platform_id'])

        # Adding model 'Image'
        db.create_table('repo_image', (
            ('id', self.gf('django.db.models.fields.AutoField')(primary_key=True)),
            ('name', self.gf('django.db.models.fields.CharField')(max_length=100)),
            ('url', self.gf('django.db.models.fields.CharField')(max_length=250)),
            ('url_file', self.gf('django.db.models.fields.CharField')(max_length=250)),
            ('urls', self.gf('django.db.models.fields.TextField')(null=True, blank=True)),
            ('container_repo', self.gf('django.db.models.fields.related.ForeignKey')(blank=True, related_name='images', null=True, to=orm['repo.Repo'])),
        ))
        db.send_create_signal('repo', ['Image'])

        # Adding M2M table for field repo on 'Image'
        m2m_table_name = db.shorten_name('repo_image_repo')
        db.create_table(m2m_table_name, (
            ('id', models.AutoField(verbose_name='ID', primary_key=True, auto_created=True)),
            ('image', models.ForeignKey(orm['repo.image'], null=False)),
            ('repo', models.ForeignKey(orm['repo.repo'], null=False))
        ))
        db.create_unique(m2m_table_name, ['image_id', 'repo_id'])

        # Adding model 'Pointer'
        db.create_table('repo_pointer', (
            ('id', self.gf('django.db.models.fields.AutoField')(primary_key=True)),
            ('name', self.gf('django.db.models.fields.CharField')(max_length=200)),
            ('public', self.gf('django.db.models.fields.BooleanField')(default=False)),
            ('factory', self.gf('django.db.models.fields.BooleanField')(default=False)),
            ('target', self.gf('django.db.models.fields.related.ForeignKey')(to=orm['repo.Repo'], unique=True)),
        ))
        db.send_create_signal('repo', ['Pointer'])

        # Adding model 'ABI'
        db.create_table('repo_abi', (
            ('id', self.gf('django.db.models.fields.AutoField')(primary_key=True)),
            ('version', self.gf('django.db.models.fields.related.ForeignKey')(to=orm['repo.Pointer'])),
            ('private', self.gf('django.db.models.fields.TextField')(blank=True)),
            ('public', self.gf('django.db.models.fields.TextField')()),
            ('files', self.gf('django.db.models.fields.TextField')(blank=True)),
            ('dump', self.gf('django.db.models.fields.CharField')(max_length=1000, blank=True)),
        ))
        db.send_create_signal('repo', ['ABI'])

        # Adding model 'Graph'
        db.create_table('repo_graph', (
            ('id', self.gf('django.db.models.fields.AutoField')(primary_key=True)),
            ('direction', self.gf('django.db.models.fields.IntegerField')()),
            ('depth', self.gf('django.db.models.fields.PositiveIntegerField')(default=3, null=True, blank=True)),
            ('image', self.gf('django.db.models.fields.related.ForeignKey')(to=orm['repo.Image'], null=True, blank=True)),
            ('packages', self.gf('django.db.models.fields.TextField')(null=True, blank=True)),
            ('dot', self.gf('django.db.models.fields.files.FileField')(max_length=100)),
            ('svg', self.gf('django.db.models.fields.files.FileField')(max_length=100, null=True)),
            ('pkg_meta', self.gf('reports.jsonfield.fields.JSONField')(null=True, blank=True)),
        ))
        db.send_create_signal('repo', ['Graph'])

        # Adding M2M table for field repo on 'Graph'
        m2m_table_name = db.shorten_name('repo_graph_repo')
        db.create_table(m2m_table_name, (
            ('id', models.AutoField(verbose_name='ID', primary_key=True, auto_created=True)),
            ('graph', models.ForeignKey(orm['repo.graph'], null=False)),
            ('repo', models.ForeignKey(orm['repo.repo'], null=False))
        ))
        db.create_unique(m2m_table_name, ['graph_id', 'repo_id'])

        # Adding model 'PackageMetaType'
        db.create_table('repo_packagemetatype', (
            ('id', self.gf('django.db.models.fields.AutoField')(primary_key=True)),
            ('name', self.gf('django.db.models.fields.CharField')(unique=True, max_length=100)),
            ('description', self.gf('django.db.models.fields.TextField')()),
            ('allow_multiple', self.gf('django.db.models.fields.BooleanField')(default=False)),
            ('default', self.gf('django.db.models.fields.related.ForeignKey')(to=orm['repo.PackageMetaChoice'], null=True, blank=True)),
        ))
        db.send_create_signal('repo', ['PackageMetaType'])

        # Adding model 'PackageMetaChoice'
        db.create_table('repo_packagemetachoice', (
            ('id', self.gf('django.db.models.fields.AutoField')(primary_key=True)),
            ('name', self.gf('django.db.models.fields.CharField')(unique=True, max_length=100)),
            ('description', self.gf('django.db.models.fields.TextField')()),
            ('metatype', self.gf('django.db.models.fields.related.ForeignKey')(related_name='choices', to=orm['repo.PackageMetaType'])),
        ))
        db.send_create_signal('repo', ['PackageMetaChoice'])


    def backwards(self, orm):
        # Removing unique constraint on 'Repo', fields ['server', 'repo_path']
        db.delete_unique('repo_repo', ['server_id', 'repo_path'])

        # Deleting model 'Arch'
        db.delete_table('repo_arch')

        # Deleting model 'DocService'
        db.delete_table('repo_docservice')

        # Deleting model 'LocalizationService'
        db.delete_table('repo_localizationservice')

        # Deleting model 'BuildService'
        db.delete_table('repo_buildservice')

        # Deleting model 'Project'
        db.delete_table('repo_project')

        # Deleting model 'Platform'
        db.delete_table('repo_platform')

        # Deleting model 'RepoServer'
        db.delete_table('repo_reposerver')

        # Deleting model 'Repo'
        db.delete_table('repo_repo')

        # Removing M2M table for field projects on 'Repo'
        db.delete_table(db.shorten_name('repo_repo_projects'))

        # Removing M2M table for field components on 'Repo'
        db.delete_table(db.shorten_name('repo_repo_components'))

        # Removing M2M table for field archs on 'Repo'
        db.delete_table(db.shorten_name('repo_repo_archs'))

        # Deleting model 'Note'
        db.delete_table('repo_note')

        # Deleting model 'IssueTracker'
        db.delete_table('repo_issuetracker')

        # Removing M2M table for field platform on 'IssueTracker'
        db.delete_table(db.shorten_name('repo_issuetracker_platform'))

        # Deleting model 'Image'
        db.delete_table('repo_image')

        # Removing M2M table for field repo on 'Image'
        db.delete_table(db.shorten_name('repo_image_repo'))

        # Deleting model 'Pointer'
        db.delete_table('repo_pointer')

        # Deleting model 'ABI'
        db.delete_table('repo_abi')

        # Deleting model 'Graph'
        db.delete_table('repo_graph')

        # Removing M2M table for field repo on 'Graph'
        db.delete_table(db.shorten_name('repo_graph_repo'))

        # Deleting model 'PackageMetaType'
        db.delete_table('repo_packagemetatype')

        # Deleting model 'PackageMetaChoice'
        db.delete_table('repo_packagemetachoice')


    models = {
        'repo.abi': {
            'Meta': {'object_name': 'ABI'},
            'dump': ('django.db.models.fields.CharField', [], {'max_length': '1000', 'blank': 'True'}),
            'files': ('django.db.models.fields.TextField', [], {'blank': 'True'}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'private': ('django.db.models.fields.TextField', [], {'blank': 'True'}),
            'public': ('django.db.models.fields.TextField', [], {}),
            'version': ('django.db.models.fields.related.ForeignKey', [], {'to': "orm['repo.Pointer']"})
        },
        'repo.arch': {
            'Meta': {'object_name': 'Arch'},
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'name': ('django.db.models.fields.CharField', [], {'unique': 'True', 'max_length': '50'})
        },
        'repo.buildservice': {
            'Meta': {'object_name': 'BuildService'},
            'apiurl': ('django.db.models.fields.CharField', [], {'unique': 'True', 'max_length': '250'}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'name': ('django.db.models.fields.CharField', [], {'unique': 'True', 'max_length': '250'}),
            'namespace': ('django.db.models.fields.CharField', [], {'unique': 'True', 'max_length': '50'}),
            'weburl': ('django.db.models.fields.CharField', [], {'max_length': '250', 'null': 'True', 'blank': 'True'})
        },
        'repo.docservice': {
            'Meta': {'object_name': 'DocService'},
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'name': ('django.db.models.fields.CharField', [], {'unique': 'True', 'max_length': '250'}),
            'weburl': ('django.db.models.fields.CharField', [], {'max_length': '250', 'null': 'True', 'blank': 'True'})
        },
        'repo.graph': {
            'Meta': {'object_name': 'Graph'},
            'depth': ('django.db.models.fields.PositiveIntegerField', [], {'default': '3', 'null': 'True', 'blank': 'True'}),
            'direction': ('django.db.models.fields.IntegerField', [], {}),
            'dot': ('django.db.models.fields.files.FileField', [], {'max_length': '100'}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'image': ('django.db.models.fields.related.ForeignKey', [], {'to': "orm['repo.Image']", 'null': 'True', 'blank': 'True'}),
            'packages': ('django.db.models.fields.TextField', [], {'null': 'True', 'blank': 'True'}),
            'pkg_meta': ('reports.jsonfield.fields.JSONField', [], {'null': 'True', 'blank': 'True'}),
            'repo': ('django.db.models.fields.related.ManyToManyField', [], {'symmetrical': 'False', 'to': "orm['repo.Repo']", 'null': 'True', 'blank': 'True'}),
            'svg': ('django.db.models.fields.files.FileField', [], {'max_length': '100', 'null': 'True'})
        },
        'repo.image': {
            'Meta': {'object_name': 'Image'},
            'container_repo': ('django.db.models.fields.related.ForeignKey', [], {'blank': 'True', 'related_name': "'images'", 'null': 'True', 'to': "orm['repo.Repo']"}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'name': ('django.db.models.fields.CharField', [], {'max_length': '100'}),
            'repo': ('django.db.models.fields.related.ManyToManyField', [], {'symmetrical': 'False', 'to': "orm['repo.Repo']", 'null': 'True', 'blank': 'True'}),
            'url': ('django.db.models.fields.CharField', [], {'max_length': '250'}),
            'url_file': ('django.db.models.fields.CharField', [], {'max_length': '250'}),
            'urls': ('django.db.models.fields.TextField', [], {'null': 'True', 'blank': 'True'})
        },
        'repo.issuetracker': {
            'Meta': {'object_name': 'IssueTracker'},
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'name': ('django.db.models.fields.CharField', [], {'unique': 'True', 'max_length': '100'}),
            'platform': ('django.db.models.fields.related.ManyToManyField', [], {'symmetrical': 'False', 'to': "orm['repo.Platform']", 'null': 'True', 'blank': 'True'}),
            're': ('django.db.models.fields.CharField', [], {'max_length': '100'}),
            'url': ('django.db.models.fields.CharField', [], {'max_length': '200'})
        },
        'repo.localizationservice': {
            'Meta': {'object_name': 'LocalizationService'},
            'apiurl': ('django.db.models.fields.CharField', [], {'max_length': '250', 'null': 'True', 'blank': 'True'}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'name': ('django.db.models.fields.CharField', [], {'unique': 'True', 'max_length': '250'}),
            'weburl': ('django.db.models.fields.CharField', [], {'max_length': '250', 'null': 'True', 'blank': 'True'})
        },
        'repo.note': {
            'Meta': {'object_name': 'Note'},
            'body': ('django.db.models.fields.TextField', [], {}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'repo': ('django.db.models.fields.related.ForeignKey', [], {'to': "orm['repo.Repo']", 'unique': 'True'})
        },
        'repo.packagemetachoice': {
            'Meta': {'object_name': 'PackageMetaChoice'},
            'description': ('django.db.models.fields.TextField', [], {}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'metatype': ('django.db.models.fields.related.ForeignKey', [], {'related_name': "'choices'", 'to': "orm['repo.PackageMetaType']"}),
            'name': ('django.db.models.fields.CharField', [], {'unique': 'True', 'max_length': '100'})
        },
        'repo.packagemetatype': {
            'Meta': {'object_name': 'PackageMetaType'},
            'allow_multiple': ('django.db.models.fields.BooleanField', [], {'default': 'False'}),
            'default': ('django.db.models.fields.related.ForeignKey', [], {'to': "orm['repo.PackageMetaChoice']", 'null': 'True', 'blank': 'True'}),
            'description': ('django.db.models.fields.TextField', [], {}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'name': ('django.db.models.fields.CharField', [], {'unique': 'True', 'max_length': '100'})
        },
        'repo.platform': {
            'Meta': {'object_name': 'Platform'},
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'name': ('django.db.models.fields.CharField', [], {'unique': 'True', 'max_length': '100'})
        },
        'repo.pointer': {
            'Meta': {'object_name': 'Pointer'},
            'factory': ('django.db.models.fields.BooleanField', [], {'default': 'False'}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'name': ('django.db.models.fields.CharField', [], {'max_length': '200'}),
            'public': ('django.db.models.fields.BooleanField', [], {'default': 'False'}),
            'target': ('django.db.models.fields.related.ForeignKey', [], {'to': "orm['repo.Repo']", 'unique': 'True'})
        },
        'repo.project': {
            'Meta': {'object_name': 'Project'},
            'buildservice': ('django.db.models.fields.related.ForeignKey', [], {'to': "orm['repo.BuildService']", 'null': 'True'}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'name': ('django.db.models.fields.CharField', [], {'max_length': '100'}),
            'request_target': ('django.db.models.fields.related.ForeignKey', [], {'blank': 'True', 'related_name': "'request_source'", 'null': 'True', 'to': "orm['repo.Project']"})
        },
        'repo.repo': {
            'Meta': {'unique_together': "(('server', 'repo_path'),)", 'object_name': 'Repo'},
            'archs': ('django.db.models.fields.related.ManyToManyField', [], {'symmetrical': 'False', 'to': "orm['repo.Arch']", 'null': 'True', 'blank': 'True'}),
            'components': ('django.db.models.fields.related.ManyToManyField', [], {'blank': 'True', 'related_name': "'containers'", 'null': 'True', 'symmetrical': 'False', 'to': "orm['repo.Repo']"}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'platform': ('django.db.models.fields.related.ForeignKey', [], {'to': "orm['repo.Platform']"}),
            'projects': ('django.db.models.fields.related.ManyToManyField', [], {'symmetrical': 'False', 'to': "orm['repo.Project']", 'null': 'True', 'blank': 'True'}),
            'release': ('django.db.models.fields.CharField', [], {'max_length': '250'}),
            'release_date': ('django.db.models.fields.DateField', [], {'null': 'True', 'blank': 'True'}),
            'repo_path': ('django.db.models.fields.CharField', [], {'max_length': '250'}),
            'server': ('django.db.models.fields.related.ForeignKey', [], {'to': "orm['repo.RepoServer']"})
        },
        'repo.reposerver': {
            'Meta': {'object_name': 'RepoServer'},
            'buildservice': ('django.db.models.fields.related.ForeignKey', [], {'to': "orm['repo.BuildService']", 'null': 'True', 'blank': 'True'}),
            'id': ('django.db.models.fields.AutoField', [], {'primary_key': 'True'}),
            'url': ('django.db.models.fields.CharField', [], {'unique': 'True', 'max_length': '250'})
        }
    }

    complete_apps = ['repo']
