import 'dart:convert';
import 'dart:typed_data';

import 'package:dio/dio.dart';
import 'package:flutter_test/flutter_test.dart';
import 'package:naryad_ai/features/assistant/data/assistant_repository.dart';

/// Отдаёт ответ сервера кусками, как настоящий SSE-поток (разрыв посреди строки).
class _SseAdapter implements HttpClientAdapter {
  _SseAdapter(this.chunks);
  final List<String> chunks;
  RequestOptions? last;

  @override
  Future<ResponseBody> fetch(
    RequestOptions options,
    Stream<Uint8List>? requestStream,
    Future<void>? cancelFuture,
  ) async {
    last = options;
    return ResponseBody(
      Stream.fromIterable(
        chunks.map((c) => Uint8List.fromList(utf8.encode(c))),
      ),
      200,
      headers: {
        Headers.contentTypeHeader: ['text/event-stream'],
      },
    );
  }

  @override
  void close({bool force = false}) {}
}

void main() {
  test(
    'поток помощника разбирается по событиям, даже если строка пришла частями',
    () async {
      final adapter = _SseAdapter([
        'data: {"type": "tool", "name": "find_orders", "label": "Ищу наряды"}\n\n',
        'data: {"type": "text", "text": "Просроч',
        'енных нет."}\n\ndata: {"type": "done"}\n\n',
      ]);
      final dio = Dio(BaseOptions(baseUrl: 'http://test/api/v1'))
        ..httpClientAdapter = adapter;

      final events = await AssistantRepository(
        dio,
      ).chat(const [ChatTurn('user', 'Что просрочено?')]).toList();

      expect(events.map((e) => e.type), ['tool', 'text', 'done']);
      expect(events[0].label, 'Ищу наряды');
      expect(events[1].text, 'Просроченных нет.');
      expect(adapter.last!.path, '/assistant/chat');
      expect(adapter.last!.data, {
        'messages': [
          {'role': 'user', 'content': 'Что просрочено?'},
        ],
      });
    },
  );
}
