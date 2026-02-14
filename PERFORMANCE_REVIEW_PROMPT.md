# Prompt na komplexný performance audit Django projektu

## KONTEXT
Tento je Django projekt `bike service` - webová aplikácia na správu servisnej služby bicyklov s nasledujúcimi modulmi:
- Správa zákazníkov a ich bicyklov
- Servisné objednávky s fotkami a statusami
- Ticket systém na komunikáciu
- SMS a Email notifikácie
- PDF generovanie protokolov

**Cieľ:** Overovať, či je kód optimalizovaný pre rýchlosť, škálovateľnosť a budúcu údržbu.

---

## KRITICKÉ OBLASTI AUDITU

### 1. DATABASE OPTIMIZÁCIA
**Kontroly:**
- [ ] Všetky ForeignKey a ManyToMany majú `related_name`
- [ ] Databázové indexy sú nastavené na pole `email` a iných frekventovaných polí
- [ ] Chýbajú db_index=True na polí ktoré sa často filtrujú (status, created_at)
- [ ] V queryách sa používa `.select_related()` a `.prefetch_related()` kde je to potrebné
- [ ] Nie sú N+1 query problémy v listovacích pohľadoch
- [ ] JSONField checklist je správne indexovaný (ak sa ním filtruje)
- [ ] Migrácie sú bezpečné a nemajú default=... na existujúcich dátach

**Otázky:**
- Koľko queries sa spustí pri zobrazení listu všetkých servisov s fotkami a ticketami?
- Či sa v admin paneli načítavajú všetky dané cez raw SQL?

---

### 2. DJANGO VIEWS & QUERYSETS
**Kontroly:**
- [ ] Views sú rozdelené na logické moduly (customer_admin_views, ticket_views, atď)
- [ ] Nie sú všetko veľké view funkcie (max 100-150 riadkov)
- [ ] Kde je potrebné, sa používajú class-based views namiesto view funkcií
- [ ] QuerySets sú filterované čo sme v najnižšej vrstve (v models.py cez managers)
- [ ] V pohľadoch sa nepoužívajú vyčíslené zoznamy (`for item in items: if item.status == 'NEW'`)
- [ ] Pagination je implementovaná v listovacích pohľadoch
- [ ] Kešovanie querysetu výsledkov pre opakované prístupy

**Otázky:**
- Máte aktuálne 1015 riadkov v `views.py` - to je príliš veľa. Majú sa rozdeliť do menších modulov?
- Sú všetky admin CRUD operácie v `customer_admin_views.py`?

---

### 3. ORM PERFORMANCE
**Kontroly:**
- [ ] V `.values()` a `.values_list()` sa vrátia len potrebné polia
- [ ] Agregácie sú spustené v databáze (`.annotate()`, `.aggregate()`), nie v Pythone
- [ ] Bulk operácie (`bulk_create`, `bulk_update`) sa používajú pre hromadné zmeny
- [ ] `.only()` a `.defer()` sa používajú na vylúčenie veľkých polí (TextField, ImageField)
- [ ] Existujú database indexy na DateTimeField polí ktoré sa používajú v `order_by()` a filtroch

**Otázky:**
- V `ServiceOrderLog` máte TextField `body` - viete že sa načítava vždy? Používate `.defer('body')`?

---

### 4. CACHING STRATÉGIA
**Kontroly:**
- [ ] Či je nastavené Redis/Memcached ako cache backend?
- [ ] Cache key stratégia je jasná a bez konfliktov
- [ ] TTL (Time To Live) hodnoty sú primerane nastavené
- [ ] Kde sú stále sa čítaní údaje (konfigurácia, referenčné tabuľky)?
- [ ] Sú implementované cache invalidácie pri update/delete?
- [ ] Používa sa cache na session storage?

**Otázky:**
- Máte nejaký caching v kóde? Vidím `settings.py` ale ľadá som cache configu...

---

### 5. ASYNC/BACKGROUND TASKS
**Kontroly:**
- [ ] Dlhé operácie (PDF generovanie, SMS/Email) sú v background taskoch (Celery)?
- [ ] Nie sú blocking operácie v view funkciách
- [ ] Retry logika a error handling pre failed tasks
- [ ] Queue monitoring a alerting je nastavené

**Otázky:**
- SMS a Email sa posielajú synchronne v views? To môže byť bottleneck.
- PDF generovanie: koľko trvá? Či sa to deje online alebo async?

---

### 6. API EFEKTÍVNOSŤ (ak máte REST API)
**Kontroly:**
- [ ] Sú endpoint a filtry (napr. `/orders?status=NEW&page=2`)
- [ ] JSON response má len potrebné polia (nie všetko)
- [ ] Existuje API rate limiting
- [ ] Sú GraphQL subsety namiesto viacerých API callsov?

---

### 7. FRONTEND OPTIMIZÁCIA
**Kontroly:**
- [ ] CSS/JS súbory sú minifikované
- [ ] Static súbory majú cache headers nastavené
- [ ] Používa sa CDN pre assets?
- [ ] AJAX requesty majú error handling a retry logiku
- [ ] Lazy loading obrázkov

**Otázky:**
- Máte veľa fotiek v `service_photos/` - ako sa prezentujú v templates?

---

### 8. AUTHENTICATION & AUTHORIZATION
**Kontroly:**
- [ ] Session timeout je primeranný
- [ ] CSRF protection je aktívna
- [ ] Password hashovanie je moderné (argon2, nie md5)
- [ ] Rate limiting na login endpoint
- [ ] Permissions sú granulárne (nie len is_staff check)

**Otázky:**
- Vidím `user_passes_test(lambda u: u.is_staff)` na mnohých miestach - lepšie by bolo vlastné permissions.

---

### 9. CODE QUALITY & MAINTAINABILITY
**Kontroly:**
- [ ] Docstrings sú na všetkých verejných funkciách a triedach
- [ ] Type hints sú kompletné
- [ ] Tests coverage je aspoň 70%
- [ ] Linting (pylint, flake8) je bez warningov
- [ ] Duplicate kód je refaktorovaný do helpery funkcie
- [ ] Naming konvencie sú konzistentné

**Otázky:**
- Vidím `from __future__ import annotations` - to je dobré
- Máte unit testy? Vidím `tests.py` ale aká je coverage?

---

### 10. BEZPEČNOSŤ
**Kontroly:**
- [ ] SQL injection - QuerySets sú chránené, parametrované queries
- [ ] XSS protection - Templating auto-escapes
- [ ] CSRF - `{% csrf_token %}`
- [ ] Input validation na všetkých forms
- [ ] Rate limiting na citlivé endpoints
- [ ] File upload bezpečnosť (MIME type, file size limity)
- [ ] Sensitive data nie je v loggoch (hesla, tokeny)

**Otázky:**
- PDF generovanie - overujete či user má právo dostať danú objednávku?

---

### 11. MONITORING & LOGGING
**Kontroly:**
- [ ] Všetky chyby sa zaznamenajú (logging, Sentry)
- [ ] Performance metriky sa zbierajú (query time, response time)
- [ ] Health checks sú implementované
- [ ] Error alerting je nastavené

---

### 12. DEPLOYMENT OPTIMIZÁCIA
**Kontroly:**
- [ ] `DEBUG = False` v produkcii
- [ ] `ALLOWED_HOSTS` sú nastavené
- [ ] Static súbory sú servované cez web server (nginx), nie Django
- [ ] Database je na inejachine ako app
- [ ] Load balancing pre multiple workers (gunicorn workers)
- [ ] Database connection pooling je nastavené

---

## ŠPECIFICKÉ PROBLÉMY NA OVERENIE

### Z `views.py` (1015 riadkov):
1. **Rozdelenie:** Rozdeľte do menších modulov:
   - `customer_views.py`
   - `admin_views.py`
   - `ticket_views.py` (už existuje)
   - `auth_views.py`

2. **Repeating code:** Skontrolujte či sa kód opakuje (helpers, decorators)

3. **Query optimization:** Skontrolujte všetky `.filter()` a `.get()` callsy

### Z `models.py`:
1. **Chýbajúce indexy:**
   ```python
   class ServiceOrder(models.Model):
       status = models.CharField(..., db_index=True)  # TODO: Pridať index
       created_at = models.DateTimeField(..., db_index=True)  # TODO: Pridať index
   ```

2. **Metadata:** Pridajte `Meta` triedy s `ordering` a `unique_together`:
   ```python
   class Meta:
       indexes = [
           models.Index(fields=['bike', '-created_at']),
       ]
       ordering = ['-created_at']
   ```

---

## VÝSTUPNÝ FORMÁT AUDITU

Pre každú oblasť uveďte:
```
### OBLASŤ: [Názov]
**Stav:** ✓ OK / ⚠ POZOR / ❌ PROBLÉM

**Zistenia:**
- Zistenie 1
- Zistenie 2

**Odporúčania:**
- Odporúčanie 1 (priorita: VYSOKÁ/STREDNÁ/NÍZKA)
- Odporúčanie 2

**Predpokladaný benefit:**
- Performance zlepšenie: X%
- Maintenance: Lepšie / Lepšie
```

---

## PRIORITNÝ CHECKLIST

🔴 **KRITICKÉ (fix hneď):**
- N+1 query problémy
- Zbytočne veľké querysets
- Synchronný processing dlhých operácií

🟠 **VYSOKÁ (fix do týždňa):**
- Chýbajúce indexy
- Duplicate kód
- Chýbajúce type hints

🟡 **STREDNÁ (fix do mesiaca):**
- Code organization
- Caching implementácia
- Monitoring setup

🟢 **NÍZKA (nice-to-have):**
- Code comments
- Documentation
- Test coverage optimization

---

## DODATOČNÉ OTÁZKY

1. Koľko active users máte?
2. Koľko servisných objednávok denne?
3. Aké sú biggest bottlenecks v produkcii (ak existuje)?
4. Máte monitoring/profiling setup?
5. Aké sú SLA requirements (availability, response time)?

