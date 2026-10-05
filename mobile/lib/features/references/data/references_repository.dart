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

  Future<References> loadAll() async {
    final results = await Future.wait([
      _list('workshops'),
      _list('equipment'),
      _list('fault-codes'),
      _list('materials'),
      _list('brigades'),
    ]);
    return References(
      workshops: [
        for (final j in results[0]) RefItem(id: j['id'], name: j['name']),
      ],
      equipment: [
        for (final j in results[1])
          RefItem(
            id: j['id'],
            name: j['name'],
            workshopId: j['workshop_id'],
            code: j['inventory_number'],
          ),
      ],
      faultCodes: [
        for (final j in results[2])
          RefItem(
            id: j['id'],
            name: j['name'],
            code: j['code'],
            category: j['category'],
          ),
      ],
      materials: [
        for (final j in results[3])
          RefItem(
            id: j['id'],
            name: j['name'],
            unit: j['unit'],
            category: j['category'],
          ),
      ],
      brigades: [
        for (final j in results[4])
          RefItem(id: j['id'], name: j['name'], workshopId: j['workshop_id']),
      ],
    );
  }

  Future<List<ExecutorStatus>> executors() async {
    final res = await _dio.get('/users/executors/availability');
    return [for (final j in res.data as List) ExecutorStatus.fromJson(j)];
  }
}

final referencesRepositoryProvider = Provider(
  (ref) => ReferencesRepository(ref.watch(dioProvider)),
);

/// Справочники кэшируются на всю сессию.
final referencesProvider = FutureProvider<References>(
  (ref) => ref.watch(referencesRepositoryProvider).loadAll(),
);
