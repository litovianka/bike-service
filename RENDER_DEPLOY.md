# Render deploy (free test)

## 1) Pushni zmeny na GitHub
Repo musí obsahovať `render.yaml`.

## 2) V Render Dashboard
- `New` -> `Blueprint`
- vyber repo
- Render načíta `render.yaml` a vytvorí:
  - Web service (`bike-service-web`)
  - Free Postgres (`bike-service-db`)

## 3) Deploy
`DATABASE_URL` sa nastaví automaticky z `bike-service-db` cez `render.yaml`.

Potom daj `Manual Deploy` -> `Deploy latest commit` (ak sa nespustí auto deploy).

## 4) Prihlásenie do adminu
V Shell pre web službu spusti:

```bash
python manage.py createsuperuser
```

## Poznámky pre free plán
- služba sa uspáva pri neaktivite
- prvý request po uspaní je pomalší
- free má limity, vhodné iba na test/demo
