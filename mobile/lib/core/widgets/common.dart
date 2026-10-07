import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:intl/intl.dart';

import '../api/api_error.dart';
import '../i18n/i18n.dart';

final dateTimeFmt = DateFormat('dd.MM HH:mm');

/// Единая обработка AsyncValue: спиннер / ошибка с повтором / данные.
class AsyncView<T> extends StatelessWidget {
  const AsyncView({
    super.key,
    required this.value,
    required this.data,
    this.onRetry,
  });

  final AsyncValue<T> value;
  final Widget Function(T data) data;
  final VoidCallback? onRetry;

  @override
  Widget build(BuildContext context) => switch (value) {
    AsyncValue(:final value?, hasValue: true) => data(value),
    AsyncValue(:final error?) => ErrorView(
      message: ApiError.from(error).message,
      onRetry: onRetry,
    ),
    _ => const Center(child: CircularProgressIndicator()),
  };
}

class ErrorView extends StatelessWidget {
  const ErrorView({super.key, required this.message, this.onRetry});

  final String message;
  final VoidCallback? onRetry;

  @override
  Widget build(BuildContext context) => Center(
    child: Padding(
      padding: const EdgeInsets.all(24),
      child: Column(
        mainAxisSize: MainAxisSize.min,
        children: [
          const Icon(Icons.cloud_off, size: 48),
          const SizedBox(height: 12),
          Text(message, textAlign: TextAlign.center),
          if (onRetry != null) ...[
            const SizedBox(height: 12),
            FilledButton.tonal(
              onPressed: onRetry,
              child: Text(tr('Повторить')),
            ),
          ],
        ],
      ),
    ),
  );
}

void showError(BuildContext context, Object error) {
  ScaffoldMessenger.of(context).showSnackBar(
    SnackBar(
      content: Text(ApiError.from(error).message),
      backgroundColor: Theme.of(context).colorScheme.error,
    ),
  );
}

/// Диалог обязательной причины (отклонение, пауза, возврат, отмена).
Future<String?> askReason(BuildContext context, String title) {
  final ctrl = TextEditingController();
  return showDialog<String>(
    context: context,
    builder: (ctx) => AlertDialog(
      title: Text(title),
      content: TextField(
        controller: ctrl,
        autofocus: true,
        maxLines: 3,
        decoration: InputDecoration(
          hintText: tr('Укажите причину'),
          border: OutlineInputBorder(),
        ),
      ),
      actions: [
        TextButton(
          onPressed: () => Navigator.pop(ctx),
          child: Text(tr('Отмена')),
        ),
        FilledButton(
          onPressed: () {
            if (ctrl.text.trim().isNotEmpty) {
              Navigator.pop(ctx, ctrl.text.trim());
            }
          },
          child: Text(tr('Подтвердить')),
        ),
      ],
    ),
  );
}

/// «осталось 1 ч 20 мин» / «просрочен на 15 мин» — как в панели.
String timeLeft(DateTime deadline, [DateTime? now]) {
  final diff = deadline.difference(now ?? DateTime.now()).inMinutes;
  final abs = diff.abs();
  final h = abs ~/ 60, m = abs % 60;
  final text = h > 0
      ? tr('{h} ч {m} мин', {'h': h, 'm': m})
      : tr('{m} мин', {'m': m});
  return diff >= 0
      ? tr('осталось {text}', {'text': text})
      : tr('просрочен на {text}', {'text': text});
}
