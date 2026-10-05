import 'package:dio/dio.dart';
import 'package:flutter_riverpod/flutter_riverpod.dart';
import 'package:image_picker/image_picker.dart';

import '../../../core/api/api_client.dart';
import '../../../core/api/api_error.dart';
import '../domain/work_order.dart';

class MaterialLine {
  MaterialLine({
    required this.materialId,
    required this.name,
    required this.unit,
    this.quantity = 1,
  });
  final int materialId;
  final String name;
  final String unit;
  double quantity;

  Map<String, dynamic> toJson() => {
    'material_id': materialId,
    'quantity': quantity,
  };
}

class NewOrder {
  NewOrder({
    required this.type,
    required this.description,
    required this.workshopId,
    required this.deadline,
    this.equipmentId,
    this.executorId,
    this.brigadeId,
    this.priority = Priority.medium,
    this.equipmentStopped = false,
  });

  OrderType type;
  String description;
  int workshopId;
  int? equipmentId;
  int? executorId;
  int? brigadeId;
  Priority priority;
  DateTime deadline;
  bool equipmentStopped;

  Map<String, dynamic> toJson() => {
    'type': type.name,
    'description': description,
    'workshop_id': workshopId,
    'equipment_id': equipmentId,
    'executor_id': executorId,
    'brigade_id': brigadeId,
    'priority': priority.name,
    'deadline': deadline.toUtc().toIso8601String(),
    'equipment_stopped': equipmentStopped,
  };
}

class OrdersRepository {
  OrdersRepository(this._dio);
  final Dio _dio;

  Future<T> _wrap<T>(Future<T> Function() call) async {
    try {
      return await call();
    } catch (e) {
      throw ApiError.from(e);
    }
  }

  Future<List<WorkOrder>> list({List<OrderStatus>? statuses}) =>
      _wrap(() async {
        final res = await _dio.get(
          '/orders',
          queryParameters: {
            if (statuses != null)
              'status': [
                for (final s in statuses)
                  s == OrderStatus.inProgress ? 'in_progress' : s.name,
              ],
          },
          options: Options(listFormat: ListFormat.multiCompatible),
        );
        return [for (final j in res.data as List) WorkOrder.fromJson(j)];
      });

  Future<OrderDetail> get(int id) => _wrap(
    () async => OrderDetail.fromJson((await _dio.get('/orders/$id')).data),
  );

  Future<OrderDetail> action(int id, OrderAction action, {String? reason}) =>
      _wrap(() async {
        final res = await _dio.post(
          '/orders/$id/actions/${action.apiName}',
          data: {'reason': reason},
        );
        return OrderDetail.fromJson(res.data);
      });

  Future<OrderDetail> uploadPhotos(
    int id, {
    required bool after,
    required List<XFile> files,
  }) => _wrap(() async {
    final form = FormData.fromMap({
      'files': [
        for (final f in files)
          await MultipartFile.fromFile(
            f.path,
            filename: f.name,
            contentType: DioMediaType('image', 'jpeg'),
          ),
      ],
    });
    final res = await _dio.post(
      '/orders/$id/photos',
      queryParameters: {'type': after ? 'after' : 'before'},
      data: form,
    );
    return OrderDetail.fromJson(res.data);
  });

  Future<OrderDetail> complete(
    int id, {
    required String report,
    required int faultCodeId,
    required List<MaterialLine> materials,
  }) => _wrap(() async {
    final res = await _dio.post(
      '/orders/$id/complete',
      data: {
        'work_report': report,
        'fault_code_id': faultCodeId,
        'materials': [for (final m in materials) m.toJson()],
      },
    );
    return OrderDetail.fromJson(res.data);
  });

  // --- мастер ---

  Future<OrderDetail> create(NewOrder order) => _wrap(
    () async => OrderDetail.fromJson(
      (await _dio.post('/orders', data: order.toJson())).data,
    ),
  );

  Future<OrderDetail> approve(int id, int score, {String? comment}) =>
      _wrap(() async {
        final res = await _dio.post(
          '/orders/$id/approve',
          data: {'master_score': score, 'comment': comment},
        );
        return OrderDetail.fromJson(res.data);
      });

  Future<OrderDetail> reassign(int id, {int? executorId, int? brigadeId}) =>
      _wrap(() async {
        final res = await _dio.post(
          '/orders/$id/reassign',
          data: {'executor_id': executorId, 'brigade_id': brigadeId},
        );
        return OrderDetail.fromJson(res.data);
      });

  Future<Map<String, List<WorkOrder>>> board() => _wrap(() async {
    final res = await _dio.get('/orders/board');
    return {
      for (final c in res.data as List)
        c['title'] as String: [
          for (final o in c['orders'] as List) WorkOrder.fromJson(o),
        ],
    };
  });

  Future<Map<String, int>> counters() => _wrap(
    () async =>
        Map<String, int>.from((await _dio.get('/dashboard/counters')).data),
  );
}

final ordersRepositoryProvider = Provider(
  (ref) => OrdersRepository(ref.watch(dioProvider)),
);
