class RefItem {
  const RefItem({
    required this.id,
    required this.name,
    this.code,
    this.unit,
    this.category,
  });

  final int id;
  final String name;
  final String? code; // шифр неисправности
  final String? unit;
  final String? category;

  String get title => code == null ? name : '$code · $name';
}

class References {
  const References({required this.faultCodes, required this.materials});

  final List<RefItem> faultCodes;
  final List<RefItem> materials;
}
