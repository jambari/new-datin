"""Model berita (artikel) untuk halaman publik dan CRUD staff."""
from django.conf import settings
from django.db import models
from django.urls import reverse
from django.utils import timezone
from django.utils.text import slugify


class BeritaQuerySet(models.QuerySet):
    def published(self):
        """Artikel yang sudah terbit dan waktunya sudah lewat."""
        return self.filter(
            status=Berita.STATUS_PUBLISHED,
            published_at__lte=timezone.now(),
        )


class Berita(models.Model):
    STATUS_DRAFT = 'draft'
    STATUS_PUBLISHED = 'published'
    STATUS_CHOICES = [
        (STATUS_DRAFT, 'Draf'),
        (STATUS_PUBLISHED, 'Terbit'),
    ]

    title = models.CharField('judul', max_length=220)
    slug = models.SlugField('slug', max_length=240, unique=True, blank=True,
                            help_text='Kosongkan untuk dibuat otomatis dari judul.')
    excerpt = models.TextField('ringkasan', blank=True,
                               help_text='Tampil di daftar berita dan kartu di beranda.')
    content = models.TextField('isi', help_text='HTML dari editor WYSIWYG.')
    cover = models.ImageField('gambar sampul', upload_to='berita/covers/%Y/%m/',
                              null=True, blank=True)
    author = models.ForeignKey(settings.AUTH_USER_MODEL, verbose_name='penulis',
                               on_delete=models.SET_NULL, null=True, blank=True,
                               related_name='berita')
    status = models.CharField('status', max_length=10, choices=STATUS_CHOICES,
                              default=STATUS_DRAFT, db_index=True)
    published_at = models.DateTimeField('waktu terbit', null=True, blank=True,
                                        db_index=True)
    views = models.PositiveIntegerField('dilihat', default=0)
    created_at = models.DateTimeField('dibuat', auto_now_add=True)
    updated_at = models.DateTimeField('diperbarui', auto_now=True)

    objects = BeritaQuerySet.as_manager()

    class Meta:
        ordering = ['-published_at', '-created_at']
        verbose_name = 'Berita'
        verbose_name_plural = 'Berita'

    def __str__(self):
        return self.title

    def save(self, *args, **kwargs):
        if not self.slug:
            self.slug = self._unique_slug()
        if self.status == self.STATUS_PUBLISHED and self.published_at is None:
            self.published_at = timezone.now()
        super().save(*args, **kwargs)

    def _unique_slug(self):
        base = slugify(self.title)[:200] or 'berita'
        slug = base
        n = 2
        while Berita.objects.filter(slug=slug).exclude(pk=self.pk).exists():
            slug = f'{base}-{n}'
            n += 1
        return slug

    def get_absolute_url(self):
        return reverse('berita:detail', args=[self.slug])

    @property
    def is_published(self):
        return (self.status == self.STATUS_PUBLISHED
                and self.published_at is not None
                and self.published_at <= timezone.now())

    @property
    def author_name(self):
        if self.author is None:
            return 'Redaksi BMKG Jayapura'
        return self.author.get_full_name() or self.author.username

    def can_edit(self, user):
        """Penulis sendiri atau superuser boleh mengubah/menghapus."""
        if not user.is_authenticated:
            return False
        return user.is_superuser or self.author_id == user.id
