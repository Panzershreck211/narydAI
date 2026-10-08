#!/usr/bin/env bash
# НарядAI — запуск одной командой (Linux / macOS).
#   ./start.sh            собрать, запустить, загрузить демо-данные, открыть панель
#   ./start.sh --no-demo  без демо-данных (панель покажет экран первичной настройки)
#   ./start.sh --no-open  не открывать браузер
#   ./start.sh --stop     остановить контейнеры (данные сохраняются)
# Порты по умолчанию: панель 8080, API 8000, PostgreSQL 5432; занятые заменяются следующими свободными.
set -euo pipefail
cd "$(dirname "$0")"

DEMO=1; OPEN=1; STOP=0
for arg in "$@"; do
  case "$arg" in
    --no-demo) DEMO=0 ;;
    --no-open) OPEN=0 ;;
    --stop)    STOP=1 ;;
    *) echo "Неизвестный параметр: $arg"; exit 1 ;;
  esac
done

step() { printf '\n\033[36m==> %s\033[0m\n' "$1"; }
# в stderr: fail вызывается и внутри $(pick_port …), где stdout перехватывается
fail() { printf '\n\033[31mОШИБКА: %s\033[0m\n' "$1" >&2; exit 1; }

# ---------- 1. Docker ----------
step "Проверяю Docker"
command -v docker >/dev/null || fail "Docker не найден. Установите Docker: https://docs.docker.com/get-docker/"
if ! docker info >/dev/null 2>&1; then
  if [[ "$(uname)" == "Darwin" ]] && [[ -d /Applications/Docker.app ]]; then
    echo "Docker Desktop не запущен — запускаю (до 3 минут)..."
    open -a Docker
    for _ in $(seq 60); do docker info >/dev/null 2>&1 && break; sleep 3; done
  fi
  docker info >/dev/null 2>&1 || fail "Docker не запущен (или нет прав: добавьте пользователя в группу docker)."
fi

COMPOSE_VER="$(docker compose version --short 2>/dev/null | sed 's/^v//')" || fail 'Нужен Docker Compose v2 (команда "docker compose").'
IFS=. read -r MAJ MIN _ <<<"${COMPOSE_VER%%[-+]*}"
if (( MAJ < 2 || (MAJ == 2 && MIN < 24) )); then
  fail "Нужен Docker Compose 2.24 или новее, установлен $COMPOSE_VER."
fi
echo "Docker Compose $COMPOSE_VER"

if (( STOP )); then
  step "Останавливаю контейнеры"
  docker compose stop
  echo "Остановлено. Данные сохранены, запуск снова — ./start.sh"
  exit 0
fi

# ---------- 2. Порты ----------
step "Подбираю свободные порты"
# свои контейнеры от прошлого запуска освобождают порты, чтобы их можно было занять снова
docker compose stop >/dev/null 2>&1 || true

dotenv() { [[ -f .env ]] && grep -E "^[[:space:]]*$1[[:space:]]*=" .env | tail -n1 | cut -d= -f2- | tr -d '[:space:]' || true; }

port_free() {
  # занят, если на нём кто-то принимает соединения
  if (exec 3<>"/dev/tcp/127.0.0.1/$1") 2>/dev/null; then return 1; fi
  return 0
}

pick_port() {
  local name=$1 def=$2 pref p
  pref="${!name:-}"; [[ -z "$pref" ]] && pref="$(dotenv "$name")"; [[ -z "$pref" ]] && pref=$def
  for (( p = pref; p < pref + 200; p++ )); do
    if port_free "$p"; then
      (( p != pref )) && printf '\033[33m  порт %s занят — %s=%s\033[0m\n' "$pref" "$name" "$p" >&2
      echo "$p"; return
    fi
  done
  fail "Не нашёл свободный порт для $name рядом с $pref"
}

WEB_PORT="$(pick_port WEB_PORT 8080)"; export WEB_PORT
API_PORT="$(pick_port API_PORT 8000)"; export API_PORT
DB_PORT="$(pick_port DB_PORT 5432)";   export DB_PORT
echo "  панель :$WEB_PORT   API :$API_PORT   PostgreSQL :$DB_PORT"

# IP компьютера в локальной сети — панель покажет его в «Настройки → Подключение мобильного приложения»
if [[ "$(uname)" == "Darwin" ]]; then
  LAN_IPS="$(for i in en0 en1 en2; do ipconfig getifaddr "$i" 2>/dev/null; done | paste -sd, -)"
else
  # адрес интерфейса с маршрутом наружу (не мосты Docker); запасной вариант — первый из hostname -I
  LAN_IPS="$(ip route get 1.1.1.1 2>/dev/null | awk '{for (i = 1; i < NF; i++) if ($i == "src") print $(i + 1)}' || true)"
  [[ -z "$LAN_IPS" ]] && LAN_IPS="$(hostname -I 2>/dev/null | awk '{print $1}' || true)"
fi
export SERVER_LAN_IPS="$LAN_IPS"
LAN="${LAN_IPS%%,*}"

# ---------- 3. Сборка и запуск ----------
step "Собираю и запускаю контейнеры (первый раз — несколько минут)"
docker compose up -d --build

step "Жду готовности API и панели"
ready=0
for _ in $(seq 90); do
  if curl -fsS "http://localhost:$API_PORT/health" >/dev/null 2>&1 &&
     curl -fsS "http://localhost:$WEB_PORT/api/v1/setup/status" >/dev/null 2>&1; then
    ready=1; break
  fi
  sleep 2
done
if (( ! ready )); then
  docker compose logs --tail 40 api
  fail "API не ответил за 3 минуты — логи выше."
fi

# ---------- 4. Демо-данные ----------
if (( DEMO )); then
  step "Загружаю демо-данные"
  docker compose exec -T api python -m app.seed
fi

# ---------- 5. Итог ----------
G='\033[32m'; N='\033[0m'
printf "\n${G}============================================================${N}\n"
printf "${G} НарядAI запущен${N}\n"
printf "${G}============================================================${N}\n"
echo " Веб-панель:   http://localhost:$WEB_PORT"
[[ -n "$LAN" ]] && echo " Из сети:      http://$LAN:$WEB_PORT"
echo " Swagger API:  http://localhost:$API_PORT/docs"
echo
if (( DEMO )); then
  echo " Демо-вход (backend/app/seed.py, только для демонстрации):"
  echo "   веб-панель:  admin / Admin#2026     master1 / Master#2026     boss / Boss#2026"
  echo "   приложение:  исполнители 1001-1004, ПИН 2580 (или пароль Worker#2026)"
else
  echo " Откройте панель — она предложит создать первого администратора."
fi
echo
if [[ -n "$LAN" ]]; then
  PHONE_ADDR="$LAN"; (( WEB_PORT != 8080 )) && PHONE_ADDR="$LAN:$WEB_PORT"
  echo " Мобильное приложение: на экране входа «Сервер → Изменить» введите $PHONE_ADDR"
  echo "   (эмулятор Android на этом компьютере — ничего вводить не нужно)"
fi
echo " Остановить: ./start.sh --stop   (данные сохраняются)"
printf "${G}============================================================${N}\n"

if (( OPEN )); then
  (xdg-open "http://localhost:$WEB_PORT" || open "http://localhost:$WEB_PORT") >/dev/null 2>&1 || true
fi
