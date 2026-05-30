-- ============================================================================
-- ALGO V1 — СКЕЛЕТ 11 КЛАСС (чистый методический файл)
-- Источник: Sardor Bozorov, PDF программа 11 класса
-- 3 разделов, 6 тем, 44 пунктов, 119 атомарных навыков
-- ============================================================================
-- ФОРМАТ: Только поля методиста. ИИ-поля (importance, typical_time_seconds,
-- irt_*, difficulty_score, weight, criticality) заполняются пайплайном.
-- Prerequisites — будут сгенерированы AI-пайплайном
-- ============================================================================

-- Очистка
DELETE FROM tasks_master WHERE skill_id LIKE 'G11_%';
DELETE FROM knowledge_hierarchy WHERE id LIKE 'G11_%';

-- ============================================================================
-- L1: РАЗДЕЛЫ (3)
-- ============================================================================
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, class_level_start, class_level_end, sequence_order)
VALUES
    ('G11_FUNC', 'L1', NULL, 'Functions и Limit', 'Функции и предел', 11, 11, 1),
    ('G11_DERIV', 'L1', NULL, 'Derivative', 'Производная', 11, 11, 2),
    ('G11_INTEG', 'L1', NULL, 'Integral', 'Интеграл', 11, 11, 3);

-- ============================================================================
-- L2: ТЕМЫ (6)
-- ============================================================================
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, class_level_start, class_level_end, sequence_order)
VALUES
    ('G11_T01', 'L2', 'G11_FUNC', 'Functions и их Transformations', 'Функции и их преобразования', 11, 11, 1),
    ('G11_T02', 'L2', 'G11_FUNC', 'Limit Functions и Continuity', 'Предел функции и непрерывность', 11, 11, 2),
    ('G11_T03', 'L2', 'G11_DERIV', 'Derivative простой и сложной Functions', 'Производная простой и сложной функции', 11, 11, 3),
    ('G11_T04', 'L2', 'G11_DERIV', 'Application Derivative', 'Применение производной', 11, 11, 4),
    ('G11_T05', 'L2', 'G11_INTEG', 'Antiderivative и Integral', 'Первообразная и интеграл', 11, 11, 5),
    ('G11_T06', 'L2', 'G11_INTEG', 'Differential Equations', 'Дифференциальные уравнения', 11, 11, 6);

-- ============================================================================
-- L3: ПУНКТЫ (44)
-- ============================================================================
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, class_level_start, class_level_end, sequence_order)
VALUES
    ('G11_P01', 'L3', 'G11_T01', 'Elementary Functions', 'Элементарные функции', 11, 11, 1),
    ('G11_P02', 'L3', 'G11_T01', 'Domain Definition и Domain изменения.', 'Область определения и область изменения.', 11, 11, 2),
    ('G11_P03', 'L3', 'G11_T01', 'Evenness Oddness Periodicity Functions', 'Чётность, нечётность, периодичность функций', 11, 11, 3),
    ('G11_P04', 'L3', 'G11_T01', 'Intervals возрастания, убывания,', 'Промежутки возрастания, убывания,', 11, 11, 4),
    ('G11_P05', 'L3', 'G11_T01', 'Investigation Functions элементарными методами', 'Исследование функций элементарными методами', 11, 11, 5),
    ('G11_P06', 'L3', 'G11_T01', 'Basic Ways Transformations of Graphs', 'Основные способы преобразования графиков', 11, 11, 6),
    ('G11_P07', 'L3', 'G11_T01', 'Graphs Functions содержащих модули', 'Графики функций, содержащих модули', 11, 11, 7),
    ('G11_P08', 'L3', 'G11_T01', 'Graphs Composite Functions', 'Графики сложных функций', 11, 11, 8),
    ('G11_P09', 'L3', 'G11_T02', 'Concept предела Functions', 'Понятие предела функции', 11, 11, 9),
    ('G11_P10', 'L3', 'G11_T02', 'One-sided Limits', 'Односторонние пределы', 11, 11, 10),
    ('G11_P11', 'L3', 'G11_T02', 'Properties of Limits Functions', 'Свойства пределов функций', 11, 11, 11),
    ('G11_P12', 'L3', 'G11_T02', 'Concept Continuity Functions', 'Понятие непрерывности функции', 11, 11, 12),
    ('G11_P13', 'L3', 'G11_T02', 'Mutually Inverse Functions', 'Взаимно обратные функции', 11, 11, 13),
    ('G11_P14', 'L3', 'G11_T02', 'Inverse Trigonometric Functions', 'Обратные тригонометрические функции', 11, 11, 14),
    ('G11_P15', 'L3', 'G11_T02', 'Examples of Using Inverse', 'Примеры использования обратных', 11, 11, 15),
    ('G11_P16', 'L3', 'G11_T03', 'Concept Derivative', 'Понятие производной', 11, 11, 16),
    ('G11_P17', 'L3', 'G11_T03', 'Derivative Sum и Difference', 'Производная суммы и разности', 11, 11, 17),
    ('G11_P18', 'L3', 'G11_T03', 'Continuity Functions Differential', 'Непрерывность функции. Дифференциал', 11, 11, 18),
    ('G11_P19', 'L3', 'G11_T03', 'Derivative Product и Quotient', 'Производная произведения и частного', 11, 11, 19),
    ('G11_P20', 'L3', 'G11_T03', 'Derivatives Elementary Functions', 'Производные элементарных функций', 11, 11, 20),
    ('G11_P21', 'L3', 'G11_T03', 'Derivative сложной Functions', 'Производная сложной функции', 11, 11, 21),
    ('G11_P22', 'L3', 'G11_T03', 'Derivative обратной Functions', 'Производная обратной функции', 11, 11, 22),
    ('G11_P23', 'L3', 'G11_T04', 'Maximum и Minimum Functions', 'Максимум и минимум функции', 11, 11, 23),
    ('G11_P24', 'L3', 'G11_T04', 'Equation Tangent Line', 'Уравнение касательной', 11, 11, 24),
    ('G11_P25', 'L3', 'G11_T04', 'Approximate Calculations', 'Приближённые вычисления', 11, 11, 25),
    ('G11_P26', 'L3', 'G11_T04', 'Theorems о среднем', 'Теоремы о среднем', 11, 11, 26),
    ('G11_P27', 'L3', 'G11_T04', 'Increase и Decrease Functions', 'Возрастание и убывание функции', 11, 11, 27),
    ('G11_P28', 'L3', 'G11_T04', 'Derivatives Higher Order', 'Производные высших порядков', 11, 11, 28),
    ('G11_P29', 'L3', 'G11_T04', 'Convexity of Graph Functions', 'Выпуклость графика функции', 11, 11, 29),
    ('G11_P30', 'L3', 'G11_T04', 'Extremum Functions с Single Critical', 'Экстремум функции с единственной критической', 11, 11, 30),
    ('G11_P31', 'L3', 'G11_T04', 'Problems на Maximum и Minimum', 'Задачи на максимум и минимум', 11, 11, 31),
    ('G11_P32', 'L3', 'G11_T04', 'Asymptotes Дробно-линейная Function', 'Асимптоты. Дробно-линейная функция', 11, 11, 32),
    ('G11_P33', 'L3', 'G11_T04', 'Construction of Graphs Functions с применением производных', 'Построение графиков функций с применением производных', 11, 11, 33),
    ('G11_P34', 'L3', 'G11_T04', 'Formula и Series Taylor', 'Формула и ряд Тейлора', 11, 11, 34),
    ('G11_P35', 'L3', 'G11_T05', 'Concept Antiderivative', 'Понятие первообразной', 11, 11, 35),
    ('G11_P36', 'L3', 'G11_T05', 'Substitution of Variable Интегрирование by Parts', 'Замена переменной. Интегрирование по частям', 11, 11, 36),
    ('G11_P37', 'L3', 'G11_T05', 'Area Curvilinear Trapezoid', 'Площадь криволинейной трапеции', 11, 11, 37),
    ('G11_P38', 'L3', 'G11_T05', 'Definite Integral', 'Определённый интеграл', 11, 11, 38),
    ('G11_P39', 'L3', 'G11_T05', 'Приближённое Computing определённого интеграла', 'Приближённое вычисление определённого интеграла', 11, 11, 39),
    ('G11_P40', 'L3', 'G11_T05', 'Formula Ньютона—Лейбница', 'Формула Ньютона—Лейбница', 11, 11, 40),
    ('G11_P41', 'L3', 'G11_T05', 'Properties определённого интеграла', 'Свойства определённого интеграла', 11, 11, 41),
    ('G11_P42', 'L3', 'G11_T05', 'Application определённых Integrals в геометрии и физике', 'Применение определённых интегралов в геометрии и физике', 11, 11, 42),
    ('G11_P43', 'L3', 'G11_T06', 'Concept дифференциального Equations', 'Понятие дифференциального уравнения', 11, 11, 43),
    ('G11_P44', 'L3', 'G11_T06', 'Problems приводящие к дифференциальным', 'Задачи, приводящие к дифференциальным', 11, 11, 44);

-- ============================================================================
-- L4: АТОМАРНЫЕ НАВЫКИ (119)
-- Каждый навык содержит: example_task, assessed_ability, difficulty_level, formula из PDF
-- ============================================================================

-- ─── П.1: Элементарные функции (3 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G11_S01_01','L4','G11_P01','Classification Functions','Классификация функций','Определите, к какому классу относится функция y = 2x³ – 5',1,'apply',11,11,
 'Определите, к какому классу относится функция y = 2x³ – 5','Различение степенных, дробных и многочленных функций.','Medium (Level B)',NULL),
('G11_S01_02','L4','G11_P01','Computing значения Functions','Вычисление значения функции','Для функции f(x) = x² + 4x найдите f(−3)',2,'apply',11,11,
 'Для функции f(x) = x² + 4x найдите f(−3)','Работа с отрицательными числами при возведении в степень.','Medium (Level B)',NULL),
('G11_S01_03','L4','G11_P01','Finding аргумента by значению Functions','Нахождение аргумента по значению функции','Дана функция f(x) = 2x – 8 При каком x значение функции равно 4?',3,'apply',11,11,
 'Дана функция f(x) = 2x – 8 При каком x значение функции равно 4?','Решение линейного уравнения относительно x.','Medium (Level B)',NULL);

-- ─── П.2: Область определения и область изменения. (5 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G11_S02_01','L4','G11_P02','ОДЗ дробной Functions','ОДЗ дробной функции','Найдите область определения функции y = 5 / (2x – 10)',1,'apply',11,11,
 'Найдите область определения функции y = 5 / (2x – 10)','Исключение значений, обращающих знаменатель в ноль.','Medium (Level B)',NULL),
('G11_S02_02','L4','G11_P02','ОДЗ Functions с корнем','ОДЗ функции с корнем','Найдите область определения функции y = √6 – 3x',2,'apply',11,11,
 'Найдите область определения функции y = √6 – 3x','Решение неравенства вида f(x) ≥ 0','Medium (Level B)',NULL),
('G11_S02_03','L4','G11_P02','Комбинированная ОДЗ','Комбинированная ОДЗ','Найдите область определения функции y = 1 / √(x² – 1)',3,'analyze',11,11,
 'Найдите область определения функции y = 1 / √(x² – 1)','Решение строгого квадратного неравенства x² – 1 > 0','High (Level C)',NULL),
('G11_S02_04','L4','G11_P02','Domain of Values by графику','Область значений по графику','Укажите область изменения функции, график которой ограничен снизу точкой (0; −2)',4,'apply',11,11,
 'Укажите область изменения функции, график которой ограничен снизу точкой (0; −2)','Считывание проекции графика на ось ОУ.','Medium (Level B)',NULL),
('G11_S02_05','L4','G11_P02','Boundedness Functions','Ограниченность функции','Докажите, что функция y = sin(x) + 3 ограничена.',5,'create',11,11,
 'Докажите, что функция y = sin(x) + 3 ограничена.','Использование известных границ тригонометрических функций.','High (Level C)',NULL);

-- ─── П.3: Чётность, нечётность, периодичность функций (3 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G11_S03_01','L4','G11_P03','Checking Functions на Evenness','Проверка функции на чётность','Является ли функция f(x) = x² + cos(x) чётной?',1,'apply',11,11,
 'Является ли функция f(x) = x² + cos(x) чётной?','Использование свойств чётности степенных и тригонометрических функций.','Medium (Level B)',NULL),
('G11_S03_02','L4','G11_P03','Графическая симметрия','Графическая симметрия','Достройте график нечётной функции, если известна его часть при x > 0',2,'apply',11,11,
 'Достройте график нечётной функции, если известна его часть при x > 0','Симметрия относительно начала координат.','Medium (Level B)',NULL),
('G11_S03_03','L4','G11_P03','Период Sum Functions','Период суммы функции','Найдите наименьший период функции y = sin(2x) + sin(5x)',3,'analyze',11,11,
 'Найдите наименьший период функции y = sin(2x) + sin(5x)','Нахождение НОК периодов отдельных функций.','High (Level C)',NULL);

-- ─── П.4: Промежутки возрастания, убывания, (3 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G11_S04_01','L4','G11_P04','Finding нулей Functions','Нахождение нулей функции','Найдите нули функции y = (x – 4)√x – 1',1,'analyze',11,11,
 'Найдите нули функции y = (x – 4)√x – 1','Решение уравнения f(x) = 0 с учетом ОДЗ.','High (Level C)',NULL),
('G11_S04_02','L4','G11_P04','Intervals Constant Sign','Промежутки знакопостоянства','При каких x график функции y = –2x + 6 находится ниже оси Ox?',2,'apply',11,11,
 'При каких x график функции y = –2x + 6 находится ниже оси Ox?','Решение неравенства f(x) < 0','Medium (Level B)',NULL),
('G11_S04_03','L4','G11_P04','Checking Functions на Monotonicity','Проверка функции на монотонность','Докажите, что функция y = 1/x убывает на промежутке',3,'create',11,11,
 'Докажите, что функция y = 1/x убывает на промежутке','Сравнение значений','High (Level C)',NULL);

-- ─── П.5: Исследование функций элементарными методами (2 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G11_S05_01','L4','G11_P05','Вершина параболы','Вершина параболы','Найдите координаты вершины функции',1,'apply',11,11,
 'Найдите координаты вершины функции','Использование формулы','Medium (Level B)',NULL),
('G11_S05_02','L4','G11_P05','Construction эскиза of Graph','Построение эскиза графика','Постройте график функции',2,'create',11,11,
 'Постройте график функции','Использование найденных характеристик функции при построении графика.','High (Level C)',NULL);

-- ─── П.6: Основные способы преобразования графиков (3 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G11_S06_01','L4','G11_P06','Сдвиг of Graph','Сдвиг графика','Как из графика',1,'apply',11,11,
 'Как из графика','Анализ горизонтального и вертикального сдвига.','Medium (Level B)',NULL),
('G11_S06_02','L4','G11_P06','Отражение of Graph','Отражение графика','Постройте график',2,'create',11,11,
 'Постройте график','Отражение относительно оси Ox.','Medium (Level B)',NULL),
('G11_S06_03','L4','G11_P06','Растяжение of Graph','Растяжение графика','Постройте график',3,'create',11,11,
 'Постройте график','Увеличение ординат точек графика в k раз.','Medium (Level B)',NULL);

-- ─── П.7: Графики функций, содержащих модули (3 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G11_S07_01','L4','G11_P07','График вида y=f(|x|)','График вида y=f(|x|)','Постройте график функции',1,'create',11,11,
 'Постройте график функции','Построение графика через зеркальное отражение правой части.','High (Level C)',NULL),
('G11_S07_02','L4','G11_P07','График вида y=|f(x)|','График вида y=|f(x)|','Постройте график функции y = |x - 2 / x + 1|',2,'create',11,11,
 'Постройте график функции y = |x - 2 / x + 1|','Отражение отрицательных частей графика вверх.','High (Level C)',NULL),
('G11_S07_03','L4','G11_P07','Графический метод Solving Equations','Графический метод решения уравнений','С помощью графиков определите количество корней уравнения |x - 1| = 2',3,'analyze',11,11,
 'С помощью графиков определите количество корней уравнения |x - 1| = 2','Нахождение точек пересечения графиков.','High (Level C)',NULL);

-- ─── П.8: Графики сложных функций (3 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G11_S08_01','L4','G11_P08','Дробно-линейная Function и Asymptotes','Дробно-линейная функция и асимптоты','Постройте график функции y = x + 3 / x - 2',1,'create',11,11,
 'Постройте график функции y = x + 3 / x - 2','Нахождение вертикальной и горизонтальной асимптот.','High (Level C)',NULL),
('G11_S08_02','L4','G11_P08','График Functions с корнем','График функции с корнем','Постройте эскиз графика y = √x - 2',2,'create',11,11,
 'Постройте эскиз графика y = √x - 2','Преобразование базового графика корня.','High (Level C)',NULL),
('G11_S08_03','L4','G11_P08','Кусочно-заданные Functions','Кусочно-заданные функции','Постройте график функции, которая равна x² при x < 0',3,'create',11,11,
 'Постройте график функции, которая равна x² при x < 0','Построение и соединение разных частей графика.','High (Level C)',NULL);

-- ─── П.9: Понятие предела функции (3 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G11_S09_01','L4','G11_P09','Интуитивное понимание предела by графику','Интуитивное понимание предела по графику','По графику функции определите значение L к которому стремится f(x) при x → a',1,'apply',11,11,
 'По графику функции определите значение L к которому стремится f(x) при x → a','Визуальный анализ поведения функции в окрестности точки.','Medium (Level B)',NULL),
('G11_S09_02','L4','G11_P09','Finding предела прямой подстановкой','Нахождение предела прямой подстановкой','Вычислите lim (x² - 3x + 2) x→4',2,'apply',11,11,
 'Вычислите lim (x² - 3x + 2) x→4','Понимание того, что для непрерывных функций предел равен значению функции в точке.','Medium (Level B)',NULL),
('G11_S09_03','L4','G11_P09','Limit Functions на бесконечности','Предел функции на бесконечности','Найдите lim 1 / x x→+∞',3,'apply',11,11,
 'Найдите lim 1 / x x→+∞','Анализ поведения дроби при бесконечно растущем знаменателе.','Medium (Level B)',NULL);

-- ─── П.10: Односторонние пределы (3 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G11_S10_01','L4','G11_P10','One-sided Limits by графику','Односторонние пределы по графику','Найдите предел функции f(x) в точке x = 2 слева и справа.',1,'apply',11,11,
 'Найдите предел функции f(x) в точке x = 2 слева и справа.','Различение направлений приближения к точке.','Medium (Level B)',NULL),
('G11_S10_02','L4','G11_P10','Односторонний Limit кусочной Functions','Односторонний предел кусочной функции','Дана функция f(x) = { x+1, x < 0 { x^2, x ≥ 0 Найдите lim f(x) x→0-0',2,'analyze',11,11,
 'Дана функция f(x) = { x+1, x < 0 { x^2, x ≥ 0 Найдите lim f(x) x→0-0','Выбор нужной ветви кусочной функции.','High (Level C)',NULL),
('G11_S10_03','L4','G11_P10','Checking существования предела','Проверка существования предела','Существует ли lim f(x) если левосторонний предел равен 3, а правосторонний равен 5?',3,'apply',11,11,
 'Существует ли lim f(x) если левосторонний предел равен 3, а правосторонний равен 5?','Проверка равенства односторонних пределов.','Medium (Level B)',NULL);

-- ─── П.11: Свойства пределов функций (3 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G11_S11_01','L4','G11_P11','Arithmetic Properties of Limits','Арифметические свойства пределов','Вычислите lim(f(x) · g(x)) если lim f(x) = 2, lim g(x) = -5',1,'apply',11,11,
 'Вычислите lim(f(x) · g(x)) если lim f(x) = 2, lim g(x) = -5','Использование свойств суммы, разности и произведения пределов.','Medium (Level B)',NULL),
('G11_S11_02','L4','G11_P11','Неопределенность вида 0/0','Неопределенность вида 0/0','Найдите lim (x^2 - 9) / (x - 3) x→3',2,'analyze',11,11,
 'Найдите lim (x^2 - 9) / (x - 3) x→3','Разложение на множители и сокращение дроби.','High (Level C)',NULL),
('G11_S11_03','L4','G11_P11','Неопределенность вида ∞/∞','Неопределенность вида ∞/∞','Вычислите lim (2x^2 + x) / (3x^2 - 5) x→∞',3,'analyze',11,11,
 'Вычислите lim (2x^2 + x) / (3x^2 - 5) x→∞','Деление числителя и знаменателя на старшую степень.','High (Level C)',NULL);

-- ─── П.12: Понятие непрерывности функции (2 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G11_S12_01','L4','G11_P12','Checking Continuity Functions','Проверка непрерывности функции','Дана функция',1,'analyze',11,11,
 'Дана функция','Выделение переменной при преобразовании дробно-линейного выражения.','High (Level C)',NULL),
('G11_S12_02','L4','G11_P12','Обратимость на промежутке','Обратимость на промежутке','Является ли функция y = x² обратимой на промежутке [−1; 0] Если да, найдите формулу обратной функции',2,'analyze',11,11,
 'Является ли функция y = x² обратимой на промежутке [−1; 0] Если да, найдите формулу обратной функции.','Выбор нужного знака при извлечении корня с учетом промежутка.','High (Level C)',NULL);

-- ─── П.13: Взаимно обратные функции (2 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G11_S13_01','L4','G11_P13','Значение обратной Functions без Formulas','Значение обратной функции без формулы','Известно, что f(x) = x⁵ + x³ + 1 Найдите значение f⁻¹(3)',1,'analyze',11,11,
 'Известно, что f(x) = x⁵ + x³ + 1 Найдите значение f⁻¹(3)','Использование свойства f(a) = b ⇔ f⁻¹(b) = a','High (Level C)',NULL),
('G11_S13_02','L4','G11_P13','Симметрия of Graphs Mutually Inverse Functions','Симметрия графиков взаимно обратных функций','Точка A(2; 5) принадлежит графику функции f(x) Какая точка принадлежит графику f⁻¹(x)',2,'apply',11,11,
 'Точка A(2; 5) принадлежит графику функции f(x) Какая точка принадлежит графику f⁻¹(x)','Симметрия относительно прямой y = x','Medium (Level B)',NULL);

-- ─── П.14: Обратные тригонометрические функции (2 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G11_S14_01','L4','G11_P14','Computing Sum аркфункций','Вычисление суммы аркфункций','Вычислите arcsin(−1/2) + arccos(−√3/2)',1,'apply',11,11,
 'Вычислите arcsin(−1/2) + arccos(−√3/2)','Использование формул для отрицательных аргументов аркфункций.','Medium (Level B)',NULL),
('G11_S14_02','L4','G11_P14','Domain Definition арккосинуса','Область определения арккосинуса','Найдите область определения функции y = arccos(2x − 5)',2,'apply',11,11,
 'Найдите область определения функции y = arccos(2x − 5)','Решение двойного неравенства −1 ≤ 2x − 5 ≤ 1','Medium (Level B)',NULL);

-- ─── П.15: Примеры использования обратных (2 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G11_S15_01','L4','G11_P15','Композиции Inverse Functions','Композиции обратных функций','Найдите точное значение sin(arcctg(-2))',1,'analyze',11,11,
 'Найдите точное значение sin(arcctg(-2))','Использование тригонометрических тождеств и вспомогательного угла.','High (Level C)',NULL),
('G11_S15_02','L4','G11_P15','Simplification выражений arcsin(sina)','Упрощение выражений arcsin(sina)','Вычислите arcsin(sin(7π/6))',2,'analyze',11,11,
 'Вычислите arcsin(sin(7π/6))','Приведение угла к основному промежутку значений arcsin.','High (Level C)',NULL);

-- ─── П.16: Понятие производной (2 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G11_S16_01','L4','G11_P16','Геометрический смысл Derivative','Геометрический смысл производной','Найдите угловой коэффициент касательной к графику функции f (x) = x² в точке x₀ = 3',1,'apply',11,11,
 'Найдите угловой коэффициент касательной к графику функции f (x) = x² в точке x₀ = 3','Использование связи','Medium (Level B)',NULL),
('G11_S16_02','L4','G11_P16','Дифференцируемость Functions','Дифференцируемость функции','Является ли функция f (x) = | x | дифференцируемой в точке x = 0',2,'analyze',11,11,
 'Является ли функция f (x) = | x | дифференцируемой в точке x = 0','Анализ существования производной в точках излома.','High (Level C)',NULL);

-- ─── П.17: Производная суммы и разности (1 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G11_S17_01','L4','G11_P17','Derivatives Functions с корнями и дробями','Производные функций с корнями и дробями','Найдите производную функции y = 3x² - √x + 3/√x',1,'apply',11,11,
 'Найдите производную функции y = 3x² - √x + 3/√x','Представление корней и дробей в степенном виде перед дифференцированием.','Medium (Level B)',NULL);

-- ─── П.18: Непрерывность функции. Дифференциал (1 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G11_S18_01','L4','G11_P18','Differential и приращение Functions','Дифференциал и приращение функции','Для функции f (x) = x² найдите дифференциал df',1,'analyze',11,11,
 'Для функции f (x) = x² найдите дифференциал df','Различение полного приращения и линейной части приращения.','High (Level C)',NULL);

-- ─── П.19: Производная произведения и частного (2 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G11_S19_01','L4','G11_P19','Derivative Product Functions','Производная произведения функций','Найдите производную функции y = x · e^x · sin x',1,'analyze',11,11,
 'Найдите производную функции y = x · e^x · sin x','Последовательное применение правила производной произведения.','High (Level C)',NULL),
('G11_S19_02','L4','G11_P19','Derivative дроби с тригонометрией','Производная дроби с тригонометрией','Найдите y''',2,'analyze',11,11,
 'Найдите y''','Использование правила производной частного и тригонометрических тождеств.','High (Level C)',NULL);

-- ─── П.20: Производные элементарных функций (1 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G11_S20_01','L4','G11_P20','Derivatives Logarithmic и Exponential Functions','Производные логарифмических и показательных функций','Найдите производную функции y = log_2(x) + 5^x',1,'apply',11,11,
 'Найдите производную функции y = log_2(x) + 5^x','Использование формул (log_a x)'' = 1 / (x ln a) и (a^x)'' = a^x ln a','Medium (Level B)',NULL);

-- ─── П.21: Производная сложной функции (1 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G11_S21_01','L4','G11_P21','Дифференцирование сложной Functions','Дифференцирование сложной функции','Найдите производную функции y = sin³(4x - 1)',1,'analyze',11,11,
 'Найдите производную функции y = sin³(4x - 1)','Применение правила цепочки для вложенных функций.','High (Level C)',NULL);

-- ─── П.22: Производная обратной функции (2 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G11_S22_01','L4','G11_P22','Finding Derivative через исходную функцию','Нахождение производной через исходную функцию','Для функции f(x) = x³ + x найдите производную обратной функции в точке y = 2 если известно, что f(1)',1,'analyze',11,11,
 'Для функции f(x) = x³ + x найдите производную обратной функции в точке y = 2 если известно, что f(1) = 2','Нахождение производной обратной функции без нахождения её формулы.','High (Level C)',NULL),
('G11_S22_02','L4','G11_P22','Derivative обратной тригонометрической Functions','Производная обратной тригонометрической функции','Найдите производную функции y = arcsin(x) используя формулу производной обратной функции для x = sin',2,'analyze',11,11,
 'Найдите производную функции y = arcsin(x) используя формулу производной обратной функции для x = sin(y)','Вывод производных аркфункций через производные тригонометрических функций.','High (Level C)',NULL);

-- ─── П.23: Максимум и минимум функции (4 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G11_S23_01','L4','G11_P23','Finding критических точек','Нахождение критических точек','Найдите критические точки функции y = x³ − 3x² + 2',1,'apply',11,11,
 'Найдите критические точки функции y = x³ − 3x² + 2','Решение уравнения f''(x) = 0','Medium (Level B)',NULL),
('G11_S23_02','L4','G11_P23','Investigation знаков Derivative','Исследование знаков производной','Определите точки максимума и минимума функции.',2,'analyze',11,11,
 'Определите точки максимума и минимума функции.','Анализ знаков производной слева и справа от критической точки.','High (Level C)',NULL),
('G11_S23_03','L4','G11_P23','Finding экстремума by второй Derivative','Нахождение экстремума по второй производной','Исследуйте функцию на экстремум с помощью f''''(x)',3,'analyze',11,11,
 'Исследуйте функцию на экстремум с помощью f''''(x)','Использование признака второй производной.','High (Level C)',NULL),
('G11_S23_04','L4','G11_P23','Наибольшее и наименьшее значение на отрезке','Наибольшее и наименьшее значение на отрезке','Найдите максимум и минимум функции на [a; b]',4,'analyze',11,11,
 'Найдите максимум и минимум функции на [a; b]','Проверка критических точек и концов отрезка.','High (Level C)',NULL);

-- ─── П.24: Уравнение касательной (4 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G11_S24_01','L4','G11_P24','Finding углового коэффициента Tangent Line','Нахождение углового коэффициента касательной','Найдите коэффициент касательной к графику функции в точке.',1,'apply',11,11,
 'Найдите коэффициент касательной к графику функции в точке.','Вычисление $k = f''(x_0)$','Medium (Level B)',NULL),
('G11_S24_02','L4','G11_P24','Составление Equations Tangent Line','Составление уравнения касательной','Составьте уравнение касательной к графику функции $y = f(x)$ в точке $x = x_0$',2,'create',11,11,
 'Составьте уравнение касательной к графику функции $y = f(x)$ в точке $x = x_0$','Использование формулы касательной.','Medium (Level B)',NULL),
('G11_S24_03','L4','G11_P24','Касательная, параллельная прямой','Касательная, параллельная прямой','Найдите точки графика, где касательная параллельна прямой $y = kx + b$',3,'analyze',11,11,
 'Найдите точки графика, где касательная параллельна прямой $y = kx + b$','Приравнивание производной коэффициенту наклона.','High (Level C)',NULL),
('G11_S24_04','L4','G11_P24','Касательная, перпендикулярная прямой','Касательная, перпендикулярная прямой','Найдите точки, где касательная перпендикулярна заданной прямой.',4,'analyze',11,11,
 'Найдите точки, где касательная перпендикулярна заданной прямой.','Использование условия $k_1 k_2 = -1$','High (Level C)',NULL);

-- ─── П.25: Приближённые вычисления (3 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G11_S25_01','L4','G11_P25','Using дифференциала','Использование дифференциала','Приближенно вычислите $\sqrt{4,1}$',1,'apply',11,11,
 'Приближенно вычислите $\sqrt{4,1}$','Применение дифференциала.','Medium (Level B)',NULL),
('G11_S25_02','L4','G11_P25','Приближённое Computing степеней','Приближённое вычисление степеней','Приближенно найдите $1,02^5$',2,'analyze',11,11,
 'Приближенно найдите $1,02^5$','Линеаризация функции.','High (Level C)',NULL),
('G11_S25_03','L4','G11_P25','Оценка погрешности','Оценка погрешности','Найдите абсолютную погрешность вычисления.',3,'analyze',11,11,
 'Найдите абсолютную погрешность вычисления.','Сравнение точного и приближенного значения.','High (Level C)',NULL);

-- ─── П.26: Теоремы о среднем (2 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G11_S26_01','L4','G11_P26','Checking условий Theorems Лагранжа','Проверка условий теоремы Лагранжа','Проверьте выполнение условий теоремы на отрезке.',1,'analyze',11,11,
 'Проверьте выполнение условий теоремы на отрезке.','Анализ непрерывности и дифференцируемости функции.','High (Level C)',NULL),
('G11_S26_02','L4','G11_P26','Finding точки с','Нахождение точки с','Найдите с ∈ (a; b) для которого выполняется теорема Лагранжа.',2,'analyze',11,11,
 'Найдите с ∈ (a; b) для которого выполняется теорема Лагранжа.','Решение уравнения по формуле Лагранжа.','High (Level C)',NULL);

-- ─── П.27: Возрастание и убывание функции (3 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G11_S27_01','L4','G11_P27','Intervals возрастания','Промежутки возрастания','Найдите промежутки возрастания функции.',1,'apply',11,11,
 'Найдите промежутки возрастания функции.','Анализ знака производной.','Medium (Level B)',NULL),
('G11_S27_02','L4','G11_P27','Intervals убывания','Промежутки убывания','Найдите промежутки убывания функции.',2,'apply',11,11,
 'Найдите промежутки убывания функции.','Исследование условия f''(x) < 0','Medium (Level B)',NULL),
('G11_S27_03','L4','G11_P27','Полное Investigation монотонности','Полное исследование монотонности','Исследуйте функцию на монотонность.',3,'analyze',11,11,
 'Исследуйте функцию на монотонность.','Метод интервалов для производной.','High (Level C)',NULL);

-- ─── П.28: Производные высших порядков (3 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G11_S28_01','L4','G11_P28','Finding второй Derivative','Нахождение второй производной','Найдите y'''' для функции y = x⁴ - 2x²',1,'apply',11,11,
 'Найдите y'''' для функции y = x⁴ - 2x²','Последовательное дифференцирование.','Medium (Level B)',NULL),
('G11_S28_02','L4','G11_P28','Finding Derivative n-го порядка','Нахождение производной n-го порядка','Найдите y(n) для степенной функции.',2,'analyze',11,11,
 'Найдите y(n) для степенной функции.','Использование закономерностей производных.','High (Level C)',NULL),
('G11_S28_03','L4','G11_P28','Физический смысл второй Derivative','Физический смысл второй производной','Найдите ускорение по закону движения.',3,'apply',11,11,
 'Найдите ускорение по закону движения.','Связь второй производной и ускорения.','Medium (Level B)',NULL);

-- ─── П.29: Выпуклость графика функции (3 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G11_S29_01','L4','G11_P29','Investigation выпуклости','Исследование выпуклости','Определите промежутки выпуклости функции.',1,'analyze',11,11,
 'Определите промежутки выпуклости функции.','Анализ знака второй производной.','High (Level C)',NULL),
('G11_S29_02','L4','G11_P29','Точки перегиба','Точки перегиба','Найдите точки перегиба графика функции.',2,'analyze',11,11,
 'Найдите точки перегиба графика функции.','Решение уравнения f''''(x) = 0 и проверка смены знака.','High (Level C)',NULL),
('G11_S29_03','L4','G11_P29','Construction of Graph с учетом выпуклости','Построение графика с учетом выпуклости','Постройте эскиз графика функции.',3,'create',11,11,
 'Постройте эскиз графика функции.','Использование свойств выпуклости и перегиба.','High (Level C)',NULL);

-- ─── П.30: Экстремум функции с единственной критической (2 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G11_S30_01','L4','G11_P30','Признак экстремума','Признак экстремума','Докажите наличие экстремума функции.',1,'create',11,11,
 'Докажите наличие экстремума функции.','Анализ смены знака производной.','High (Level C)',NULL),
('G11_S30_02','L4','G11_P30','Единственная критическая точка','Единственная критическая точка','Исследуйте функцию с одной критической точкой.',2,'analyze',11,11,
 'Исследуйте функцию с одной критической точкой.','Полное исследование поведения функции.','High (Level C)',NULL);

-- ─── П.31: Задачи на максимум и минимум (3 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G11_S31_01','L4','G11_P31','Geometric оптимизация','Геометрическая оптимизация','Найдите максимальную площадь фигуры.',1,'analyze',11,11,
 'Найдите максимальную площадь фигуры.','Составление функции и поиск экстремума.','High (Level C)',NULL),
('G11_S31_02','L4','G11_P31','Экономические Problems','Экономические задачи','Найдите максимальную прибыль.',2,'analyze',11,11,
 'Найдите максимальную прибыль.','Исследование прикладной функции.','High (Level C)',NULL),
('G11_S31_03','L4','G11_P31','Оптимизация с ограничениями','Оптимизация с ограничениями','Найдите минимальное значение функции при условии.',3,'analyze',11,11,
 'Найдите минимальное значение функции при условии.','Работа с областью допустимых значений.','High (Level C)',NULL);

-- ─── П.32: Асимптоты. Дробно-линейная функция (4 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G11_S32_01','L4','G11_P32','Вертикальные Asymptotes','Вертикальные асимптоты','Найдите вертикальные асимптоты функции.',1,'apply',11,11,
 'Найдите вертикальные асимптоты функции.','Анализ нулей знаменателя.','Medium (Level B)',NULL),
('G11_S32_02','L4','G11_P32','Горизонтальные Asymptotes','Горизонтальные асимптоты','Найдите горизонтальную асимптоту функции.',2,'apply',11,11,
 'Найдите горизонтальную асимптоту функции.','Вычисление пределов при','Medium (Level B)',NULL),
('G11_S32_03','L4','G11_P32','Наклонные Asymptotes','Наклонные асимптоты','Найдите наклонную асимптоту графика функции.',3,'analyze',11,11,
 'Найдите наклонную асимптоту графика функции.','Деление многочленов и выделение линейной части.','High (Level C)',NULL),
('G11_S32_04','L4','G11_P32','Investigation дробно-линейной Functions','Исследование дробно-линейной функции','Постройте график функции',4,'create',11,11,
 'Постройте график функции','Анализ асимптот и центра гиперболы.','High (Level C)',NULL);

-- ─── П.33: Построение графиков функций с применением производных (3 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G11_S33_01','L4','G11_P33','Полное Investigation Functions','Полное исследование функции','Исследуйте функцию и постройте её график.',1,'create',11,11,
 'Исследуйте функцию и постройте её график.','Комплексное применение производных.','High (Level C)',NULL),
('G11_S33_02','L4','G11_P33','Finding ключевых характеристик of Graph','Нахождение ключевых характеристик графика','Найдите нули, экстремумы и точки перегиба функции.',2,'analyze',11,11,
 'Найдите нули, экстремумы и точки перегиба функции.','Полный анализ поведения функции.','High (Level C)',NULL),
('G11_S33_03','L4','G11_P33','Construction of Graph рациональной Functions','Построение графика рациональной функции','Постройте график рациональной функции с асимптотами.',3,'create',11,11,
 'Постройте график рациональной функции с асимптотами.','Использование пределов и производных.','High (Level C+)',NULL);

-- ─── П.34: Формула и ряд Тейлора (3 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G11_S34_01','L4','G11_P34','Factorization Functions by формуле Taylor','Разложение функции по формуле Тейлора','Разложите функцию',1,'analyze',11,11,
 'Разложите функцию','Использование формулы Тейлора.','High (Level C)',NULL),
('G11_S34_02','L4','G11_P34','Factorization около точки','Разложение около точки','Найдите разложение функции около точки',2,'analyze',11,11,
 'Найдите разложение функции около точки','Подстановка производных в формулу ряда.','High (Level C)',NULL),
('G11_S34_03','L4','G11_P34','Приближенные Calculations с рядом Taylor','Приближенные вычисления с рядом Тейлора','Приближенно вычислите значение функции.',3,'analyze',11,11,
 'Приближенно вычислите значение функции.','Использование первых членов ряда для приближений.','High (Level C)',NULL);

-- ─── П.35: Понятие первообразной (3 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G11_S35_01','L4','G11_P35','Finding Antiderivative степенной Functions','Нахождение первообразной степенной функции','Найдите первообразную функции',1,'apply',11,11,
 'Найдите первообразную функции','Применение формулы интегрирования степенной функции.','Medium (Level B)',NULL),
('G11_S35_02','L4','G11_P35','Finding общей Antiderivative','Нахождение общей первообразной','Найдите все первообразные функции',2,'apply',11,11,
 'Найдите все первообразные функции','Добавление произвольной константы','Medium (Level B)',NULL),
('G11_S35_03','L4','G11_P35','Checking Antiderivative','Проверка первообразной','Проверьте, является ли функция',3,'analyze',11,11,
 'Проверьте, является ли функция','Проверка равенства','High (Level C)',NULL);

-- ─── П.36: Замена переменной. Интегрирование по частям (3 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G11_S36_01','L4','G11_P36','Метод замены of Variable','Метод замены переменной','Вычислите',1,'analyze',11,11,
 'Вычислите','Введение новой переменной','High (Level C)',NULL),
('G11_S36_02','L4','G11_P36','Интегрирование by Parts','Интегрирование по частям','Вычислите',2,'analyze',11,11,
 'Вычислите','Выбор функций','High (Level C)',NULL),
('G11_S36_03','L4','G11_P36','Комбинированное Application методов','Комбинированное применение методов','Вычислите сложный интеграл с заменой и интегрированием по частям.',3,'analyze',11,11,
 'Вычислите сложный интеграл с заменой и интегрированием по частям.','Последовательное применение нескольких методов интегрирования.','High (Level C)',NULL);

-- ─── П.37: Площадь криволинейной трапеции (3 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G11_S37_01','L4','G11_P37','Area под графиком Functions','Площадь под графиком функции','Найдите площадь фигуры, ограниченной графиком функции и осью Ох.',1,'apply',11,11,
 'Найдите площадь фигуры, ограниченной графиком функции и осью Ох.','Использование определённого интеграла как площади.','Medium (Level B)',NULL),
('G11_S37_02','L4','G11_P37','Area между двумя графиками','Площадь между двумя графиками','Найдите площадь между графиками функций.',2,'analyze',11,11,
 'Найдите площадь между графиками функций.','Использование формулы','High (Level C)',NULL),
('G11_S37_03','L4','G11_P37','Геометрический Analysis of Graph','Геометрический анализ графика','Определите границы интегрирования по рисунку.',3,'apply',11,11,
 'Определите границы интегрирования по рисунку.','Работа с графиками функций.','Medium (Level B)',NULL);

-- ─── П.38: Определённый интеграл (3 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G11_S38_01','L4','G11_P38','Computing определённого интеграла','Вычисление определённого интеграла','Вычислите',1,'apply',11,11,
 'Вычислите','Подстановка пределов интегрирования.','Medium (Level B)',NULL),
('G11_S38_02','L4','G11_P38','Definite Integral от нечётной Functions','Определённый интеграл от нечётной функции','Вычислите',2,'analyze',11,11,
 'Вычислите','Использование свойств симметрии.','High (Level C)',NULL),
('G11_S38_03','L4','G11_P38','Definite Integral от чётной Functions','Определённый интеграл от чётной функции','Вычислите определённый интеграл чётной функции на симметричном промежутке.',3,'analyze',11,11,
 'Вычислите определённый интеграл чётной функции на симметричном промежутке.','Применение формулы ∫₋ₐᵃ f(x) dx = 2 ∫₀ᵃ f(x) dx','High (Level C)',NULL);

-- ─── П.39: Приближённое вычисление определённого интеграла (3 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G11_S39_01','L4','G11_P39','Метод прямоугольников','Метод прямоугольников','Приближенно вычислите интеграл методом прямоугольников.',1,'analyze',11,11,
 'Приближенно вычислите интеграл методом прямоугольников.','Разбиение отрезка и вычисление суммы площадей.','High (Level C)',NULL),
('G11_S39_02','L4','G11_P39','Метод трапеций','Метод трапеций','Приближенно вычислите интеграл методом трапеции.',2,'analyze',11,11,
 'Приближенно вычислите интеграл методом трапеции.','Использование формулы площади трапеции.','High (Level C)',NULL),
('G11_S39_03','L4','G11_P39','Оценка точности приближения','Оценка точности приближения','Сравните приближенное и точное значения интеграла.',3,'analyze',11,11,
 'Сравните приближенное и точное значения интеграла.','Анализ погрешности вычислений.','High (Level C)',NULL);

-- ─── П.40: Формула Ньютона—Лейбница (3 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G11_S40_01','L4','G11_P40','Application Formulas Ньютона—Лейбница','Применение формулы Ньютона—Лейбница','Вычислите определённый интеграл через первообразную.',1,'apply',11,11,
 'Вычислите определённый интеграл через первообразную.','Подстановка верхнего и нижнего пределов.','Medium (Level B)',NULL),
('G11_S40_02','L4','G11_P40','Finding Antiderivative перед вычислением','Нахождение первообразной перед вычислением','Найдите интеграл функции, предварительно определив первообразную.',2,'analyze',11,11,
 'Найдите интеграл функции, предварительно определив первообразную.','Совмещение методов интегрирования и формулы Ньютона—Лейбница.','High (Level C)',NULL),
('G11_S40_03','L4','G11_P40','Checking вычислений','Проверка вычислений','Проверьте правильность вычисления интеграла.',3,'analyze',11,11,
 'Проверьте правильность вычисления интеграла.','Контроль вычислений через дифференцирование.','High (Level C)',NULL);

-- ─── П.41: Свойства определённого интеграла (3 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G11_S41_01','L4','G11_P41','Линейность интеграла','Линейность интеграла','Разложите интеграл суммы функций.',1,'apply',11,11,
 'Разложите интеграл суммы функций.','Использование свойства линейности.','Medium (Level B)',NULL),
('G11_S41_02','L4','G11_P41','Смена of Limits интегрирования','Смена пределов интегрирования','Измените порядок пределов интегрирования.',2,'apply',11,11,
 'Измените порядок пределов интегрирования.','Работа со знаком интеграла.','Medium (Level B)',NULL),
('G11_S41_03','L4','G11_P41','Integral на нулевом промежутке','Интеграл на нулевом промежутке','Вычислите $\int_a^b f(x) dx$',3,'apply',11,11,
 'Вычислите $\int_a^b f(x) dx$','Использование свойств определённого интеграла.','Medium (Level B)',NULL);

-- ─── П.42: Применение определённых интегралов в геометрии и физике (3 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G11_S42_01','L4','G11_P42','Finding площади фигуры','Нахождение площади фигуры','Найдите площадь фигуры с помощью интеграла.',1,'analyze',11,11,
 'Найдите площадь фигуры с помощью интеграла.','Геометрический смысл определённого интеграла.','High (Level C)',NULL),
('G11_S42_02','L4','G11_P42','Finding пути by скорости','Нахождение пути по скорости','Найдите путь по известной функции скорости.',2,'analyze',11,11,
 'Найдите путь по известной функции скорости.','Физический смысл интеграла.','High (Level C)',NULL),
('G11_S42_03','L4','G11_P42','Объём Solids of Revolution','Объём тела вращения','Найдите объём тела вращения.',3,'analyze',11,11,
 'Найдите объём тела вращения.','Использование интегралов в пространственных задачах.','High (Level C)',NULL);

-- ─── П.43: Понятие дифференциального уравнения (3 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G11_S43_01','L4','G11_P43','Checking Solving дифференциального Equations','Проверка решения дифференциального уравнения','Проверьте, является ли функция решением уравнения.',1,'apply',11,11,
 'Проверьте, является ли функция решением уравнения.','Подстановка функции и её производной в уравнение.','Medium (Level B)',NULL),
('G11_S43_02','L4','G11_P43','Простейшее Differential Equation','Простейшее дифференциальное уравнение','Решите уравнение $y'' = 3x^2$',2,'apply',11,11,
 'Решите уравнение $y'' = 3x^2$','Переход к первообразной.','Medium (Level B)',NULL),
('G11_S43_03','L4','G11_P43','Начальные условия','Начальные условия','Найдите частное решение при заданном условии.',3,'analyze',11,11,
 'Найдите частное решение при заданном условии.','Определение постоянной $C$ по начальному условию.','High (Level C)',NULL);

-- ─── П.44: Задачи, приводящие к дифференциальным (3 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G11_S44_01','L4','G11_P44','Моделирование роста','Моделирование роста','Составьте дифференциальное уравнение для роста величины.',1,'create',11,11,
 'Составьте дифференциальное уравнение для роста величины.','Перевод условия задачи на язык производных.','High (Level C)',NULL),
('G11_S44_02','L4','G11_P44','Закон движения','Закон движения','Составьте уравнение движения по известной скорости.',2,'create',11,11,
 'Составьте уравнение движения по известной скорости.','Связь координаты и скорости.','High (Level C)',NULL),
('G11_S44_03','L4','G11_P44','Прикладные Problems','Прикладные задачи','Решите физическую или биологическую задачу через дифференциальное уравнение.',3,'analyze',11,11,
 'Решите физическую или биологическую задачу через дифференциальное уравнение.','Построение математической модели процесса.','High (Level C)',NULL);
