import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';

import '../../../core/api/api_client.dart';
import '../domain/references.dart';

class ReferencesRepository {
  ReferencesRepository(this._dio);
  final Dio _dio;

  Future<List<Map<String, dynamic>>> _list(String path) async {
    final res = await _dio.get('/refs/$path');
    return (res.data as List).cast<Map<String, dynamic>>();
  }

  /// Для закрытия наряда нужны только шифры неисправностей и материалы.
  Future<References> loadAll() async {
    final results = await Future.wait([
      _list('fault-codes'),
      _list('materials'),
    ]);
    return References(
      faultCodes: [
        for (final j in results[0])
          RefItem(
            id: j['id'],
            name: j['name'],
            code: j['code'],
            category: j['category'],
          ),
      ],
      materials: [
        for (final j in results[1])
          RefItem(
            id: j['id'],
            name: j['name'],
            unit: j['unit'],
            category: j['category'],
          ),
      ],
    );
  }
}

final referencesRepositoryProvider = Provider(
  (ref) => ReferencesRepository(ref.watch(dioProvider)),
);

/// Справочники кэшируются на всю сессию.
final referencesProvider = FutureProvider<References>(
  (ref) => ref.watch(referencesRepositoryProvider).loadAll(),
);
