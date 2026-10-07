import 'dart:convert';

import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/api/api_client.dart';

/// Реплика диалога: role — user | assistant.
class ChatTurn {
  const ChatTurn(this.role, this.content);
  final String role;
  final String content;

  Map<String, String> toJson() => {'role': role, 'content': content};
}

/// Событие потока ответа (как в веб-панели): text | tool | error | done.
class ChatEvent {
  const ChatEvent(this.type, {this.text, this.label, this.message});
  final String type;
  final String? text;
  final String? label;
  final String? message;

  factory ChatEvent.fromJson(Map<String, dynamic> j) => ChatEvent(
    j['type'] as String,
    text: j['text'] as String?,
    label: j['label'] as String?,
    message: j['message'] as String?,
  );
}

class AssistantRepository {
  AssistantRepository(this._dio);
  final Dio _dio;

  Future<bool> configured() async {
    final res = await _dio.get('/assistant/status');
    return res.data['configured'] == true;
  }

  /// Ответ помощника (Gemini на сервере) по частям — Server-Sent Events.
  Stream<ChatEvent> chat(List<ChatTurn> history) async* {
    final res = await _dio.post<ResponseBody>(
      '/assistant/chat',
      data: {'messages': history.map((t) => t.toJson()).toList()},
      options: Options(
        responseType: ResponseType.stream,
        receiveTimeout: const Duration(minutes: 3),
        headers: {'Accept': 'text/event-stream'},
      ),
    );
    final lines = res.data!.stream
        .cast<List<int>>()
        .transform(utf8.decoder)
        .transform(const LineSplitter());
    await for (final line in lines) {
      if (!line.startsWith('data: ')) continue;
      yield ChatEvent.fromJson(
        jsonDecode(line.substring(6)) as Map<String, dynamic>,
      );
    }
  }
}

final assistantRepositoryProvider = Provider<AssistantRepository>(
  (ref) => AssistantRepository(ref.watch(dioProvider)),
);

final assistantConfiguredProvider = FutureProvider.autoDispose<bool>(
  (ref) => ref.watch(assistantRepositoryProvider).configured(),
);
