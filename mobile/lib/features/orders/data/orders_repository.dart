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
          '/orders/$id/actions/${action.name}',
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
}

final ordersRepositoryProvider = Provider(
  (ref) => OrdersRepository(ref.watch(dioProvider)),
);
