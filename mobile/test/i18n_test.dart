import 'dart:io';

import 'package:flutter_test/flutter_test.dart';
import 'package:naryad_ai/core/i18n/kk.dart';

/// Русские строки в коде приложения: каждая должна иметь казахский перевод.
/// Строки без перевода — название продукта, логотип, единица «шт» (уходит на сервер как данные)
/// и названия языков (их пишут каждое на своём языке).
const _keep = {'НарядAI', 'Н', 'шт', 'Тіл / Язык', 'Қазақша', 'Русский'};
final _cyr = RegExp('[А-Яа-яЁё]');
final _literal = RegExp(r"'((?:[^'\\n]|\.)*)'");

Map<String, String> _russianLiterals() {
  final found = <String, String>{};
  final files = Directory('lib')
      .listSync(recursive: true)
      .whereType<File>()
      .where((f) => f.path.endsWith('.dart') && !f.path.endsWith('kk.dart'));
  for (final file in files) {
    final lines = file.readAsLinesSync();
    for (var i = 0; i < lines.length; i++) {
      final code = lines[i].split('//').first;
      for (final m in _literal.allMatches(code)) {
        final text = m.group(1)!;
        if (_cyr.hasMatch(text) && !_keep.contains(text)) {
          found[text] = '${file.path}:${i + 1}';
        }
      }
    }
  }
  return found;
}

void main() {
  final literals = _russianLiterals();

  test('в русских строках нет интерполяции — только tr(…, {подстановки})', () {
    final bad = literals.entries.where((e) => e.key.contains(r'$'));
    expect(bad.map((e) => '${e.value} ${e.key}'), isEmpty);
  });

  test('у каждой русской строки есть казахский перевод', () {
    final missing = literals.entries.where((e) => !kk.containsKey(e.key));
    expect(missing.map((e) => '${e.value}  ${e.key}'), isEmpty);
  });

  test('подстановки {x} в переводе те же, что в оригинале', () {
    List<String> names(String s) =>
        RegExp(r'\{(\w+)\}').allMatches(s).map((m) => m.group(1)!).toList()
          ..sort();
    final broken = kk.entries.where(
      (e) => names(e.key).join() != names(e.value).join(),
    );
    expect(broken.map((e) => e.key), isEmpty);
  });
}
