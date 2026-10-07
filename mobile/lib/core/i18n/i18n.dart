import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:shared_preferences/shared_preferences.dart';

import 'kk.dart';

/// Язык интерфейса: русский (основной) и казахский.
enum AppLang {
  ru('Рус'),
  kk('Қаз');

  const AppLang(this.short);
  final String short;

  Locale get locale => Locale(name);
}

AppLang _current = AppLang.ru;

/// Текущий язык — для заголовка Accept-Language и ?lang= у WebSocket.
AppLang get currentLang => _current;

/// Перевод строки интерфейса. Ключ — русский текст, подстановки — {name}.
/// Приложение при смене языка перестраивается целиком (см. NaryadApp), поэтому
/// tr() можно вызывать прямо в build без подписки на провайдер.
String tr(String ru, [Map<String, Object?> params = const {}]) {
  var text = _current == AppLang.kk ? (kk[ru] ?? ru) : ru;
  params.forEach((k, v) => text = text.replaceAll('{$k}', '${v ?? ''}'));
  return text;
}

// Язык — не секрет: хранится в обычных настройках приложения. В зашифрованном хранилище
// (там лежат токены) значение после обновления APK оказывалось устаревшим.
const _key = 'lang';

/// Читает сохранённый язык до запуска приложения — без «мигания» русского.
Future<void> loadLang() async {
  try {
    final v = await SharedPreferencesAsync().getString(_key);
    _current = v == 'kk' ? AppLang.kk : AppLang.ru;
  } catch (_) {
    _current = AppLang.ru;
  }
}

class LangController extends Notifier<AppLang> {
  @override
  AppLang build() => _current;

  Future<void> set(AppLang lang) async {
    _current = lang;
    state = lang;
    await SharedPreferencesAsync().setString(_key, lang.name);
  }
}

final langProvider = NotifierProvider<LangController, AppLang>(
  LangController.new,
);

/// Кнопка «Қаз | Рус» для шапки и экрана входа.
class LangButton extends ConsumerWidget {
  const LangButton({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final lang = ref.watch(langProvider);
    return Padding(
      padding: const EdgeInsets.symmetric(horizontal: 4),
      child: SegmentedButton<AppLang>(
        showSelectedIcon: false,
        style: const ButtonStyle(
          visualDensity: VisualDensity(horizontal: -3, vertical: -3),
          tapTargetSize: MaterialTapTargetSize.shrinkWrap,
        ),
        segments: [
          for (final l in [AppLang.kk, AppLang.ru])
            ButtonSegment(value: l, label: Text(l.short)),
        ],
        selected: {lang},
        onSelectionChanged: (s) => ref.read(langProvider.notifier).set(s.first),
      ),
    );
  }
}

/// Компактный выбор языка для шапки: иконка, по нажатию — меню «Қазақша / Русский».
class LangMenuButton extends ConsumerWidget {
  const LangMenuButton({super.key});

  @override
  Widget build(BuildContext context, WidgetRef ref) {
    final lang = ref.watch(langProvider);
    return PopupMenuButton<AppLang>(
      tooltip: 'Тіл / Язык',
      icon: const Icon(Icons.translate),
      initialValue: lang,
      onSelected: (l) => ref.read(langProvider.notifier).set(l),
      itemBuilder: (_) => [
        for (final (l, title) in [
          (AppLang.kk, 'Қазақша'),
          (AppLang.ru, 'Русский'),
        ])
          CheckedPopupMenuItem(
            value: l,
            checked: l == lang,
            child: Text(title),
          ),
      ],
    );
  }
}
