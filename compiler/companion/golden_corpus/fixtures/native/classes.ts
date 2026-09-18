// Fields, methods, constructor, getters/setters, static members, inheritance, super.
class Shape {
  protected name: string;

  constructor(name: string) {
    this.name = name;
  }

  describe(): string {
    return this.name;
  }

  get label(): string {
    return this.name;
  }

  set label(value: string) {
    this.name = value;
  }

  static create(name: string): Shape {
    return new Shape(name);
  }
}

class Circle extends Shape {
  radius: number;
  static count = 0;

  constructor(radius: number) {
    super('circle');
    this.radius = radius;
    Circle.count++;
  }

  area(): number {
    return 3.14 * this.radius * this.radius;
  }

  describe(): string {
    return super.describe() + ' r=' + this.radius;
  }
}

export function build(): number {
  const c = new Circle(4);
  c.label = 'round';
  return c.area() + Circle.count + c.describe().length + Shape.create('x').label.length;
}
