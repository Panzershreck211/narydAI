class RefItem {
  const RefItem({
    required this.id,
    required this.name,
    this.workshopId,
    this.code,
    this.unit,
    this.category,
  });

  final int id;
  final String name;
  final int? workshopId;
  final String? code; // шифр неисправности / инв. номер
  final String? unit;
  final String? category;

  String get title => code == null ? name : '$code · $name';
}

enum Availability {
  free('Свободен'),
  busy('В работе'),
  queued('Есть очередь'),
  offShift('Не на смене');

  const Availability(this.label);
  final String label;

  static Availability parse(String v) =>
      v == 'off_shift' ? offShift : Availability.values.byName(v);
}

class ExecutorStatus {
  const ExecutorStatus({
    required this.id,
    required this.fio,
    required this.specialty,
    required this.availability,
    required this.activeOrders,
    required this.queuedOrders,
  });

  final int id;
  final String fio;
  final String? specialty;
  final Availability availability;
  final int activeOrders;
  final int queuedOrders;

  factory ExecutorStatus.fromJson(Map<String, dynamic> j) => ExecutorStatus(
    id: j['id'],
    fio: j['fio'],
    specialty: j['specialty'],
    availability: Availability.parse(j['availability']),
    activeOrders: j['active_orders'],
    queuedOrders: j['queued_orders'],
  );
}

class References {
  const References({
    required this.workshops,
    required this.equipment,
    required this.faultCodes,
    required this.materials,
    required this.brigades,
  });

  final List<RefItem> workshops;
  final List<RefItem> equipment;
  final List<RefItem> faultCodes;
  final List<RefItem> materials;
  final List<RefItem> brigades;
}
