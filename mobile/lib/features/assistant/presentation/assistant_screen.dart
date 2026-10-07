import 'dart:async';

import 'package:flutter/material.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:go_router/go_router.dart';

import '../../../core/api/api_error.dart';
import '../../../core/i18n/i18n.dart';
import '../../../core/theme/app_theme.dart';
import '../../../core/widgets/common.dart';
import '../data/assistant_repository.dart';

/// Состояние чата: переписка живёт, пока пользователь в приложении (как и в панели — без сервера).
class ChatState {
  const ChatState({
    this.turns = const [],
    this.busy = false,
    this.activity,
    this.error,
  });
  final List<ChatTurn> turns;
  final bool busy;
  final String? activity;
  final String? error;

  ChatState copyWith({
    List<ChatTurn>? turns,
    bool? busy,
    String? activity,
    String? error,
  }) => ChatState(
    turns: turns ?? this.turns,
    busy: busy ?? this.busy,
    activity: activity,
    error: error,
  );
}

class ChatController extends Notifier<ChatState> {
  StreamSubscription<ChatEvent>? _sub;

  @override
  ChatState build() {
    ref.onDispose(() => _sub?.cancel());
    return const ChatState();
  }

  void send(String question) {
    final q = question.trim();
    if (q.isEmpty || state.busy) return;
    // на сервер — последние 20 реплик, только текст
    final history = [...state.turns, ChatTurn('user', q)];
    final sent = history.length > 20
        ? history.sublist(history.length - 20)
        : history;
    state = ChatState(
      turns: [...history, const ChatTurn('assistant', '')],
      busy: true,
    );
    var answer = '';

    void finish({String? error}) {
      final turns = [...state.turns];
      if (answer.isEmpty) turns.removeLast(); // пустой ответ не показываем
      state = ChatState(turns: turns, error: error);
    }

    _sub = ref
        .read(assistantRepositoryProvider)
        .chat(sent)
        .listen(
          (e) {
            switch (e.type) {
              case 'text':
                answer += e.text ?? '';
                state = state.copyWith(
                  turns: [
                    ...state.turns.sublist(0, state.turns.length - 1),
                    ChatTurn('assistant', answer),
                  ],
                );
              case 'tool':
                state = state.copyWith(activity: e.label);
              case 'error':
                finish(error: e.message);
              case 'done':
                finish();
            }
          },
          onError: (Object err) => finish(error: ApiError.from(err).message),
          onDone: () {
            if (state.busy) finish();
          },
        );
  }

  void stop() {
    _sub?.cancel();
    state = state.copyWith(busy: false);
  }

  void clear() {
    _sub?.cancel();
    state = const ChatState();
  }
}

final chatProvider = NotifierProvider<ChatController, ChatState>(
  ChatController.new,
);

// Подсказки — ключи перевода, как в панели
const _suggestions = [
  'Какие у меня наряды?',
  'Что у меня просрочено?',
  'Как закрыть наряд?',
];

class AssistantScreen extends ConsumerStatefulWidget {
  const AssistantScreen({super.key});

  @override
  ConsumerState<AssistantScreen> createState() => _AssistantScreenState();
}

class _AssistantScreenState extends ConsumerState<AssistantScreen> {
  final _input = TextEditingController();
  final _scroll = ScrollController();

  @override
  void dispose() {
    _input.dispose();
    _scroll.dispose();
    super.dispose();
  }

  void _send([String? text]) {
    ref.read(chatProvider.notifier).send(text ?? _input.text);
    _input.clear();
  }

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final chat = ref.watch(chatProvider);
    final configured = ref.watch(assistantConfiguredProvider);

    // новые сообщения — к низу списка
    ref.listen(chatProvider, (_, _) {
      WidgetsBinding.instance.addPostFrameCallback((_) {
        if (_scroll.hasClients) {
          _scroll.jumpTo(_scroll.position.maxScrollExtent);
        }
      });
    });

    return Scaffold(
      appBar: AppBar(
        title: Text(tr('ИИ-помощник')),
        actions: [
          if (chat.turns.isNotEmpty)
            IconButton(
              tooltip: tr('Начать заново'),
              icon: const Icon(Icons.refresh),
              onPressed: ref.read(chatProvider.notifier).clear,
            ),
        ],
      ),
      body: AsyncView(
        value: configured,
        onRetry: () => ref.invalidate(assistantConfiguredProvider),
        data: (ok) => !ok
            ? _Empty(
                icon: Icons.key_off_outlined,
                title: tr('Помощник ещё не подключён.'),
                text: tr(
                  'Попросите администратора добавить ключ Gemini в разделе «Настройки».',
                ),
              )
            : Column(
                children: [
                  Expanded(
                    child: chat.turns.isEmpty
                        ? _Empty(
                            icon: Icons.auto_awesome,
                            title: tr('Отвечает по данным НарядAI'),
                            text: tr(
                              'Спросите о нарядах, исполнителях, простоях или о том, как что-то сделать в системе.',
                            ),
                            chips: [
                              for (final s in _suggestions)
                                ActionChip(
                                  label: Text(tr(s)),
                                  onPressed: () => _send(tr(s)),
                                ),
                            ],
                          )
                        : ListView.builder(
                            controller: _scroll,
                            padding: const EdgeInsets.all(12),
                            itemCount: chat.turns.length,
                            itemBuilder: (_, i) => _Bubble(turn: chat.turns[i]),
                          ),
                  ),
                  if (chat.busy)
                    Padding(
                      padding: const EdgeInsets.symmetric(
                        horizontal: 16,
                        vertical: 4,
                      ),
                      child: Row(
                        children: [
                          const SizedBox(
                            width: 14,
                            height: 14,
                            child: CircularProgressIndicator(strokeWidth: 2),
                          ),
                          const SizedBox(width: 8),
                          Expanded(
                            child: Text(
                              '${chat.activity ?? tr('Думаю')}…',
                              style: TextStyle(color: c.muted, fontSize: 13),
                            ),
                          ),
                        ],
                      ),
                    ),
                  if (chat.error != null)
                    Container(
                      width: double.infinity,
                      margin: const EdgeInsets.fromLTRB(12, 0, 12, 6),
                      padding: const EdgeInsets.all(10),
                      decoration: BoxDecoration(
                        color: c.redSoft,
                        borderRadius: BorderRadius.circular(8),
                      ),
                      child: Text(chat.error!, style: TextStyle(color: c.red)),
                    ),
                  SafeArea(
                    top: false,
                    child: Padding(
                      padding: const EdgeInsets.fromLTRB(12, 4, 8, 8),
                      child: Row(
                        children: [
                          Expanded(
                            child: TextField(
                              controller: _input,
                              minLines: 1,
                              maxLines: 4,
                              maxLength: 4000,
                              textInputAction: TextInputAction.send,
                              onSubmitted: (_) => _send(),
                              decoration: InputDecoration(
                                hintText: tr('Вопрос помощнику'),
                                counterText: '',
                              ),
                            ),
                          ),
                          const SizedBox(width: 4),
                          chat.busy
                              ? IconButton.filledTonal(
                                  tooltip: tr('Стоп'),
                                  icon: const Icon(Icons.stop),
                                  onPressed: ref
                                      .read(chatProvider.notifier)
                                      .stop,
                                )
                              : IconButton.filled(
                                  tooltip: tr('Отправить'),
                                  icon: const Icon(Icons.send),
                                  onPressed: () => _send(),
                                ),
                        ],
                      ),
                    ),
                  ),
                ],
              ),
      ),
    );
  }
}

class _Bubble extends StatelessWidget {
  const _Bubble({required this.turn});
  final ChatTurn turn;

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    final mine = turn.role == 'user';
    return Align(
      alignment: mine ? Alignment.centerRight : Alignment.centerLeft,
      child: Container(
        constraints: BoxConstraints(
          maxWidth: MediaQuery.sizeOf(context).width * 0.85,
        ),
        margin: const EdgeInsets.symmetric(vertical: 4),
        padding: const EdgeInsets.symmetric(horizontal: 12, vertical: 9),
        decoration: BoxDecoration(
          color: mine ? c.primary : c.surface,
          border: mine ? null : Border.all(color: c.border),
          borderRadius: BorderRadius.circular(12),
        ),
        child: SelectableText.rich(
          TextSpan(children: _rich(turn.content)),
          style: TextStyle(color: mine ? Colors.white : c.text, height: 1.35),
        ),
      ),
    );
  }
}

/// Простейшая разметка ответа: **жирный** и маркеры списков «* » → «• ».
List<TextSpan> _rich(String text) {
  final normalized = text.replaceAllMapped(
    RegExp(r'^(\s*)[*-] ', multiLine: true),
    (m) => '${m[1]}• ',
  );
  final spans = <TextSpan>[];
  final bold = RegExp(r'\*\*(.+?)\*\*');
  var last = 0;
  for (final m in bold.allMatches(normalized)) {
    spans.add(TextSpan(text: normalized.substring(last, m.start)));
    spans.add(
      TextSpan(
        text: m[1],
        style: const TextStyle(fontWeight: FontWeight.w700),
      ),
    );
    last = m.end;
  }
  spans.add(TextSpan(text: normalized.substring(last)));
  return spans;
}

class _Empty extends StatelessWidget {
  const _Empty({
    required this.icon,
    required this.title,
    required this.text,
    this.chips = const [],
  });
  final IconData icon;
  final String title;
  final String text;
  final List<Widget> chips;

  @override
  Widget build(BuildContext context) {
    final c = context.colors;
    return Center(
      child: SingleChildScrollView(
        padding: const EdgeInsets.all(24),
        child: Column(
          mainAxisSize: MainAxisSize.min,
          children: [
            Icon(icon, size: 44, color: c.primary),
            const SizedBox(height: 12),
            Text(
              title,
              style: Theme.of(context).textTheme.titleMedium,
              textAlign: TextAlign.center,
            ),
            const SizedBox(height: 6),
            Text(
              text,
              style: TextStyle(color: c.muted),
              textAlign: TextAlign.center,
            ),
            if (chips.isNotEmpty) ...[
              const SizedBox(height: 16),
              Wrap(
                spacing: 8,
                runSpacing: 8,
                alignment: WrapAlignment.center,
                children: chips,
              ),
            ],
          ],
        ),
      ),
    );
  }
}

/// Кнопка помощника внизу экрана: «✦ Помощник».
class AssistantButton extends StatelessWidget {
  const AssistantButton({super.key});

  @override
  Widget build(BuildContext context) => FloatingActionButton.extended(
    heroTag: 'assistant',
    tooltip: tr('ИИ-помощник'),
    onPressed: () => context.push('/assistant'),
    icon: const Icon(Icons.auto_awesome),
    label: Text(tr('Помощник')),
  );
}
