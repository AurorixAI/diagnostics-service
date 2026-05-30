-- ============================================================================
-- ALGO V1 — СКЕЛЕТ 9 КЛАСС (чистый методический файл)
-- Источник: Sardor Bozorov, PDF программа 9 класса
-- 5 разделов, 10 тем, 38 пунктов, 214 атомарных навыков
-- ============================================================================
-- ФОРМАТ: Только поля методиста. ИИ-поля (importance, typical_time_seconds,
-- irt_*, difficulty_score, weight, criticality) заполняются пайплайном.
-- Prerequisites — будут сгенерированы AI-пайплайном
-- ============================================================================

-- Очистка
DELETE FROM tasks_master WHERE skill_id LIKE 'G9_%';
DELETE FROM knowledge_hierarchy WHERE id LIKE 'G9_%';

-- ============================================================================
-- L1: РАЗДЕЛЫ (5)
-- ============================================================================
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, class_level_start, class_level_end, sequence_order)
VALUES
    ('G9_FUNC',  'L1', NULL, 'Functions and Inequalities', 'Функции. Неравенства', 9, 9, 1),
    ('G9_SYS',  'L1', NULL, 'Systems of Equations and Inequalities', 'Системы уравнений и неравенств', 9, 9, 2),
    ('G9_TRIG',  'L1', NULL, 'Trigonometry', 'Тригонометрия', 9, 9, 3),
    ('G9_PROG',  'L1', NULL, 'Progressions', 'Прогрессии', 9, 9, 4),
    ('G9_STAT',  'L1', NULL, 'Statistics and Probability', 'Статистика и теория вероятностей', 9, 9, 5);

-- ============================================================================
-- L2: ТЕМЫ (10)
-- ============================================================================
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, class_level_start, class_level_end, sequence_order)
VALUES
    ('G9_T01', 'L2', 'G9_FUNC', 'Quadratic Function', 'Квадратичная функция', 9, 9, 1),
    ('G9_T02', 'L2', 'G9_FUNC', 'Quadratic Inequality and Interval Method', 'Квадратное неравенство и метод интервалов', 9, 9, 2),
    ('G9_T03', 'L2', 'G9_FUNC', 'Function Problems', 'Задачи на функции', 9, 9, 3),
    ('G9_T04', 'L2', 'G9_SYS', 'Systems of Second and Higher Degree Equations', 'Системы уравнений второго и высокого порядка', 9, 9, 4),
    ('G9_T05', 'L2', 'G9_SYS', 'Systems of Second and Higher Degree Inequalities', 'Системы неравенств второго и высокого порядка', 9, 9, 5),
    ('G9_T06', 'L2', 'G9_TRIG', 'Introduction to Trigonometry', 'Начало тригонометрии', 9, 9, 6),
    ('G9_T07', 'L2', 'G9_TRIG', 'Trigonometric Simplification Formulas', 'Формулы тригонометрических упрощений', 9, 9, 7),
    ('G9_T08', 'L2', 'G9_PROG', 'Arithmetic Progression', 'Арифметическая прогрессия', 9, 9, 8),
    ('G9_T09', 'L2', 'G9_PROG', 'Geometric Progression', 'Геометрическая прогрессия', 9, 9, 9),
    ('G9_T10', 'L2', 'G9_STAT', 'Probability Theory', 'Теория вероятностей', 9, 9, 10);

-- ============================================================================
-- L3: ПУНКТЫ (38)
-- ============================================================================
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, class_level_start, class_level_end, sequence_order)
VALUES
    -- Тема 1
    ('G9_P01', 'L3', 'G9_T01', 'Definition of Quadratic Function', 'Определение квадратичной функции', 9, 9, 1),
    ('G9_P02', 'L3', 'G9_T01', 'Function y equals x squared', 'Функция y = x²', 9, 9, 2),
    ('G9_P03', 'L3', 'G9_T01', 'Function y equals ax squared', 'Функция y = ax²', 9, 9, 3),
    ('G9_P04', 'L3', 'G9_T01', 'Function y equals ax2 plus bx plus c', 'Функция y = ax² + bx + c', 9, 9, 4),
    ('G9_P05', 'L3', 'G9_T01', 'Graphing Quadratic Function', 'Построение графика квадратичной функции', 9, 9, 5),
    -- Тема 2
    ('G9_P06', 'L3', 'G9_T02', 'Quadratic Inequality', 'Квадратное неравенство', 9, 9, 6),
    ('G9_P07', 'L3', 'G9_T02', 'Solving Quadratic Inequality by Graph', 'Решение квадратного неравенства с помощью графика', 9, 9, 7),
    ('G9_P08', 'L3', 'G9_T02', 'Interval Method', 'Метод интервалов', 9, 9, 8),
    -- Тема 3
    ('G9_P09', 'L3', 'G9_T03', 'Domain of Function', 'Область определения функции', 9, 9, 9),
    ('G9_P10', 'L3', 'G9_T03', 'Increasing and Decreasing', 'Возрастание и убывание функции', 9, 9, 10),
    ('G9_P11', 'L3', 'G9_T03', 'Even and Odd Functions', 'Чётность и нечётность функции', 9, 9, 11),
    ('G9_P12', 'L3', 'G9_T03', 'Equations and Inequalities with Power', 'Неравенства и уравнения с участием степени', 9, 9, 12),
    -- Тема 4
    ('G9_P13', 'L3', 'G9_T04', 'Simplest Systems of Second Degree', 'Решение простейших систем уравнений 2-й степени', 9, 9, 13),
    ('G9_P14', 'L3', 'G9_T04', 'Various Methods of Solving Systems', 'Различные способы решения систем уравнений', 9, 9, 14),
    -- Тема 5
    ('G9_P15', 'L3', 'G9_T05', 'Systems of Second Degree Inequalities', 'Системы неравенств 2-й степени', 9, 9, 15),
    ('G9_P16', 'L3', 'G9_T05', 'Proving Simple Inequalities', 'Доказательство простейших неравенств', 9, 9, 16),
    -- Тема 6
    ('G9_P17', 'L3', 'G9_T06', 'Radian Measure of Angle', 'Радианная мера угла', 9, 9, 17),
    ('G9_P18', 'L3', 'G9_T06', 'Rotation of Point Around Origin', 'Поворот точки вокруг начала координат', 9, 9, 18),
    ('G9_P19', 'L3', 'G9_T06', 'Definition of sin cos tan ctg', 'Определение sin, cos, tg, ctg', 9, 9, 19),
    ('G9_P20', 'L3', 'G9_T06', 'Signs of sin cos tan', 'Знаки sin, cos, tg по четвертям', 9, 9, 20),
    -- Тема 7
    ('G9_P21', 'L3', 'G9_T07', 'Relations Between sin cos tan', 'Связь между sin, cos, tg, ctg', 9, 9, 21),
    ('G9_P22', 'L3', 'G9_T07', 'Trigonometric Identities', 'Тригонометрические тождества', 9, 9, 22),
    ('G9_P23', 'L3', 'G9_T07', 'sin cos tan of Alpha and Negative Alpha', 'sin, cos, tg углов α и −α', 9, 9, 23),
    ('G9_P24', 'L3', 'G9_T07', 'Addition Formulas', 'Формулы сложения', 9, 9, 24),
    ('G9_P25', 'L3', 'G9_T07', 'Double Angle Formulas', 'Синус и косинус двойного угла', 9, 9, 25),
    ('G9_P26', 'L3', 'G9_T07', 'Reduction Formulas', 'Формулы приведения', 9, 9, 26),
    ('G9_P27', 'L3', 'G9_T07', 'Sum and Difference of sin and cos', 'Сумма и разность синусов и косинусов', 9, 9, 27),
    -- Тема 8
    ('G9_P28', 'L3', 'G9_T08', 'Number Sequences', 'Числовые последовательности', 9, 9, 28),
    ('G9_P29', 'L3', 'G9_T08', 'Arithmetic Progression', 'Арифметическая прогрессия', 9, 9, 29),
    ('G9_P30', 'L3', 'G9_T08', 'Sum of n First Terms of AP', 'Сумма n первых членов арифметической прогрессии', 9, 9, 30),
    -- Тема 9
    ('G9_P31', 'L3', 'G9_T09', 'Geometric Progression', 'Геометрическая прогрессия', 9, 9, 31),
    ('G9_P32', 'L3', 'G9_T09', 'Sum of n First Terms of GP', 'Сумма n первых членов геометрической прогрессии', 9, 9, 32),
    ('G9_P33', 'L3', 'G9_T09', 'Infinite Decreasing GP', 'Бесконечно убывающая геометрическая прогрессия', 9, 9, 33),
    -- Тема 10
    ('G9_P34', 'L3', 'G9_T10', 'Events', 'События', 9, 9, 34),
    ('G9_P35', 'L3', 'G9_T10', 'Probability of Event', 'Вероятность события', 9, 9, 35),
    ('G9_P36', 'L3', 'G9_T10', 'Relative Frequency', 'Относительная частота случайного события', 9, 9, 36),
    ('G9_P37', 'L3', 'G9_T10', 'Random Variables', 'Случайные величины', 9, 9, 37),
    ('G9_P38', 'L3', 'G9_T10', 'Numerical Characteristics of Random Variables', 'Числовые характеристики случайных величин', 9, 9, 38);

-- ============================================================================
-- L4: АТОМАРНЫЕ НАВЫКИ (214)
-- Каждый навык содержит: example_task, assessed_ability, difficulty_level, formula из PDF
-- ============================================================================

-- ─── П.1: Определение квадратичной функции (5 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G9_S01_01','L4','G9_P01','Recognize quadratic function','Распознавание квадратичной функции','Является ли функция y = 3x² − 2x + 1 квадратичной',1,'recall',9,9,
 'Является ли функция y = 3x² − 2x + 1 квадратичной','Определение функции вида y = ax² + bx + c','Low (Level A)','y=ax²+bx+c'),
('G9_S01_02','L4','G9_P01','Identify coefficients a b c','Определение коэффициентов a, b, c','Найдите a, b, c в функции y = −2x² + 5x − 3',2,'recall',9,9,
 'Найдите a, b, c в функции y = −2x² + 5x − 3','Выделение коэффициентов квадратичной функции','Low (Level A)',NULL),
('G9_S01_03','L4','G9_P01','Direction of parabola','Направление ветвей параболы','Определите, куда направлены ветви параболы y = −x² + 3',3,'apply',9,9,
 'Определите, куда направлены ветви параболы y = −x² + 3','Анализ знака коэффициента a','Medium (Level B)',NULL),
('G9_S01_04','L4','G9_P01','Find vertex','Нахождение вершины параболы','Найдите вершину параболы y = x² − 4x + 3',4,'analyze',9,9,
 'Найдите вершину параболы y = x² − 4x + 3','Вычисление координат вершины','High (Level C)','x₀=−b/(2a)'),
('G9_S01_05','L4','G9_P01','Axis of symmetry','Определение оси симметрии','Найдите ось симметрии параболы y = 2x² − 8x + 5',5,'analyze',9,9,
 'Найдите ось симметрии параболы y = 2x² − 8x + 5','Определение x₀ = −b/(2a)','High (Level C)',NULL);

-- ─── П.2: Функция y = x² (5 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G9_S02_01','L4','G9_P02','Build table for y=x^2','Таблица значений y = x²','Составьте таблицу значений функции y = x² для x от −3 до 3',1,'recall',9,9,
 'Составьте таблицу значений функции y = x² для x от −3 до 3','Вычисление значений функции','Low (Level A)',NULL),
('G9_S02_02','L4','G9_P02','Graph of y=x^2','Построение графика y = x²','Постройте график функции y = x²',2,'apply',9,9,
 'Постройте график функции y = x²','Построение параболы по точкам','Medium (Level B)',NULL),
('G9_S02_03','L4','G9_P02','Properties of y=x^2','Свойства функции y = x²','Найдите наименьшее значение функции y = x²',3,'apply',9,9,
 'Найдите наименьшее значение функции y = x²','Определение свойств функции из графика','Medium (Level B)',NULL),
('G9_S02_04','L4','G9_P02','Symmetry of y=x^2','Симметрия графика y = x²','Покажите, что f(−2) = f(2) для функции y = x²',4,'apply',9,9,
 'Покажите, что f(−2) = f(2) для функции y = x²','Понимание чётности функции y = x²','Medium (Level B)',NULL),
('G9_S02_05','L4','G9_P02','Intersection with line','Пересечение параболы с прямой','Найдите точки пересечения y = x² и y = 4',5,'analyze',9,9,
 'Найдите точки пересечения y = x² и y = 4','Решение уравнения x² = 4','High (Level C)',NULL);

-- ─── П.3: Функция y = ax² (5 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G9_S03_01','L4','G9_P03','Graph of y=ax^2 narrow','График y = ax² при a > 1','Постройте графики y = x² и y = 2x² на одной плоскости',1,'apply',9,9,
 'Постройте графики y = x² и y = 2x² на одной плоскости','Понимание влияния коэффициента на ширину параболы','Medium (Level B)',NULL),
('G9_S03_02','L4','G9_P03','Graph of y=ax^2 wide','График y = ax² при 0 < a < 1','Постройте график y = 0.5x²',2,'apply',9,9,
 'Постройте график y = 0.5x²','Понимание влияния малого коэффициента','Medium (Level B)',NULL),
('G9_S03_03','L4','G9_P03','Negative a','График при отрицательном a','Постройте график y = −x²',3,'apply',9,9,
 'Постройте график y = −x²','Понимание отражения параболы','Medium (Level B)',NULL),
('G9_S03_04','L4','G9_P03','Compare parabolas','Сравнение парабол','Какой график шире: y = 3x² или y = 0.5x²',4,'analyze',9,9,
 'Какой график шире: y = 3x² или y = 0.5x²','Анализ влияния коэффициента на форму','High (Level C)',NULL),
('G9_S03_05','L4','G9_P03','Match equation to graph','Сопоставление уравнения и графика','Определите, какому графику соответствует уравнение y = −2x²',5,'analyze',9,9,
 'Определите, какому графику соответствует уравнение y = −2x²','Определение направления и ширины параболы','High (Level C)',NULL);

-- ─── П.4: Функция y = ax² + bx + c (5 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G9_S04_01','L4','G9_P04','Compute vertex','Вычисление вершины параболы','Найдите вершину параболы y = x² − 6x + 8',1,'apply',9,9,
 'Найдите вершину параболы y = x² − 6x + 8','Применение формулы x₀ = −b/(2a)','Medium (Level B)','x₀=−b/(2a)'),
('G9_S04_02','L4','G9_P04','Y coordinate of vertex','Нахождение y-координаты вершины','Найдите y₀ для функции y = x² − 4x + 3',2,'apply',9,9,
 'Найдите y₀ для функции y = x² − 4x + 3','Подстановка x₀ в функцию','Medium (Level B)','y₀=f(x₀)'),
('G9_S04_03','L4','G9_P04','Zeros of function','Нули квадратичной функции','Найдите нули функции y = x² − 5x + 6',3,'analyze',9,9,
 'Найдите нули функции y = x² − 5x + 6','Решение квадратного уравнения ax² + bx + c = 0','High (Level C)',NULL),
('G9_S04_04','L4','G9_P04','Y-intercept','Точка пересечения с осью Oy','Найдите точку пересечения y = 2x² − 3x + 1 с осью Oy',4,'apply',9,9,
 'Найдите точку пересечения y = 2x² − 3x + 1 с осью Oy','Вычисление f(0)','Medium (Level B)',NULL),
('G9_S04_05','L4','G9_P04','Min or max value','Наименьшее или наибольшее значение','Найдите наименьшее значение функции y = x² − 4x + 7',5,'analyze',9,9,
 'Найдите наименьшее значение функции y = x² − 4x + 7','Определение значения в вершине параболы','High (Level C)',NULL);

-- ─── П.5: Построение графика квадратичной функции (5 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G9_S05_01','L4','G9_P05','Full graphing algorithm','Полный алгоритм построения','Постройте график функции y = x² − 2x − 3',1,'analyze',9,9,
 'Постройте график функции y = x² − 2x − 3','Нахождение вершины, нулей и построение по точкам','High (Level C)',NULL),
('G9_S05_02','L4','G9_P05','Graph with no real roots','Построение при отсутствии корней','Постройте график функции y = x² + 2x + 3',2,'analyze',9,9,
 'Постройте график функции y = x² + 2x + 3','Построение параболы, не пересекающей ось Ox','High (Level C)',NULL),
('G9_S05_03','L4','G9_P05','Graph by vertex and direction','Построение по вершине и направлению','Постройте параболу с вершиной (1; −4) и ветвями вверх',3,'apply',9,9,
 'Постройте параболу с вершиной (1; −4) и ветвями вверх','Использование параметров для построения','Medium (Level B)',NULL),
('G9_S05_04','L4','G9_P05','Determine properties from graph','Определение свойств по графику','По графику определите знак коэффициента a и координаты вершины',4,'apply',9,9,
 'По графику определите знак коэффициента a и координаты вершины','Чтение графика квадратичной функции','Medium (Level B)',NULL),
('G9_S05_05','L4','G9_P05','Real-world application','Задача прикладного характера','Мяч брошен вверх: h(t) = −5t² + 20t. Найдите максимальную высоту',5,'analyze',9,9,
 'Мяч брошен вверх: h(t) = −5t² + 20t. Найдите максимальную высоту','Нахождение вершины параболы в прикладной задаче','High (Level C)',NULL);

-- ─── П.6: Квадратное неравенство (5 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G9_S06_01','L4','G9_P06','Recognize quadratic inequality','Распознавание квадратного неравенства','Является ли неравенство x² − 5x + 6 > 0 квадратным',1,'recall',9,9,
 'Является ли неравенство x² − 5x + 6 > 0 квадратным','Определение вида неравенства','Low (Level A)',NULL),
('G9_S06_02','L4','G9_P06','Solve from graph','Решение по графику','По графику y = x² − 5x + 6 определите, где y > 0',2,'apply',9,9,
 'По графику y = x² − 5x + 6 определите, где y > 0','Определение промежутков по положению графика','Medium (Level B)',NULL),
('G9_S06_03','L4','G9_P06','Solve ax^2+bx+c>0','Решение неравенства вида ax² + bx + c > 0','Решите неравенство x² − 4x + 3 > 0',3,'analyze',9,9,
 'Решите неравенство x² − 4x + 3 > 0','Нахождение корней и определение знака на промежутках','High (Level C)',NULL),
('G9_S06_04','L4','G9_P06','Solve ax^2+bx+c<0','Решение неравенства вида ax² + bx + c < 0','Решите неравенство x² − 5x + 6 < 0',4,'analyze',9,9,
 'Решите неравенство x² − 5x + 6 < 0','Выбор промежутков, где парабола ниже оси Ox','High (Level C)',NULL),
('G9_S06_05','L4','G9_P06','Inequality with no roots','Неравенство без корней','Решите неравенство x² + 4 > 0',5,'apply',9,9,
 'Решите неравенство x² + 4 > 0','Анализ случая D < 0','Medium (Level B)',NULL);

-- ─── П.7: Решение квадратного неравенства с помощью графика (4 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G9_S07_01','L4','G9_P07','Graph and inequality','Использование графика','С помощью графика y = x² − 4 решите неравенство x² − 4 ≤ 0',1,'apply',9,9,
 'С помощью графика y = x² − 4 решите неравенство x² − 4 ≤ 0','Определение промежутков по расположению графика','Medium (Level B)',NULL),
('G9_S07_02','L4','G9_P07','Non-strict inequality','Нестрогое неравенство','Решите неравенство x² − 6x + 9 ≤ 0',2,'analyze',9,9,
 'Решите неравенство x² − 6x + 9 ≤ 0','Учёт включённых границ','High (Level C)',NULL),
('G9_S07_03','L4','G9_P07','Negative leading coefficient','Отрицательный коэффициент при x²','Решите неравенство −x² + 4x − 3 ≥ 0',3,'analyze',9,9,
 'Решите неравенство −x² + 4x − 3 ≥ 0','Анализ при a < 0','High (Level C)',NULL),
('G9_S07_04','L4','G9_P07','Describe solution set','Описание множества решений','Запишите множество решений неравенства x² − 1 < 0 в виде промежутка',4,'analyze',9,9,
 'Запишите множество решений неравенства x² − 1 < 0 в виде промежутка','Переход от графического решения к интервальной записи','High (Level C)',NULL);

-- ─── П.8: Метод интервалов (4 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G9_S08_01','L4','G9_P08','Factor and find roots','Разложение на множители и нахождение корней','Методом интервалов решите (x − 1)(x − 3) > 0',1,'apply',9,9,
 'Методом интервалов решите (x − 1)(x − 3) > 0','Определение знака произведения на промежутках','Medium (Level B)',NULL),
('G9_S08_02','L4','G9_P08','Interval method for quadratic','Метод интервалов для квадратного неравенства','Решите неравенство x² − 7x + 10 > 0 методом интервалов',2,'analyze',9,9,
 'Решите неравенство x² − 7x + 10 > 0 методом интервалов','Нахождение корней, расстановка знаков','High (Level C)',NULL),
('G9_S08_03','L4','G9_P08','Three or more factors','Три и более множителей','Решите неравенство (x + 1)(x − 2)(x − 5) > 0 методом интервалов',3,'analyze',9,9,
 'Решите неравенство (x + 1)(x − 2)(x − 5) > 0 методом интервалов','Расстановка знаков на числовой прямой','High (Level C)',NULL),
('G9_S08_04','L4','G9_P08','Repeated root','Кратный корень','Решите неравенство (x − 3)² · (x + 1) ≤ 0 методом интервалов',4,'analyze',9,9,
 'Решите неравенство (x − 3)² · (x + 1) ≤ 0 методом интервалов','Учёт чётности кратности корня','High (Level C)',NULL);

-- ─── П.9: Область определения функции (3 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G9_S09_01','L4','G9_P09','Domain with fraction','ОДЗ с дробью','Найдите область определения функции y = 1/(x − 2)',1,'apply',9,9,
 'Найдите область определения функции y = 1/(x − 2)','Определение значения, при котором знаменатель равен нулю','Medium (Level B)',NULL),
('G9_S09_02','L4','G9_P09','Domain with root','ОДЗ с корнем','Найдите область определения функции y = √(x − 3)',2,'apply',9,9,
 'Найдите область определения функции y = √(x − 3)','Решение неравенства подкоренного выражения','Medium (Level B)',NULL),
('G9_S09_03','L4','G9_P09','Combined restrictions','Комбинированные ограничения','Найдите область определения функции y = √(x)/(x − 1)',3,'analyze',9,9,
 'Найдите область определения функции y = √(x)/(x − 1)','Учёт нескольких условий для ОДЗ','High (Level C)',NULL);

-- ─── П.10: Возрастание и убывание функции (3 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G9_S10_01','L4','G9_P10','Increasing function','Определение возрастания','Определите промежуток возрастания функции y = x²',1,'apply',9,9,
 'Определите промежуток возрастания функции y = x²','Понимание определения возрастающей функции','Medium (Level B)',NULL),
('G9_S10_02','L4','G9_P10','Decreasing function','Определение убывания','На каком промежутке функция y = −x² + 4 убывает',2,'apply',9,9,
 'На каком промежутке функция y = −x² + 4 убывает','Анализ поведения функции','Medium (Level B)',NULL),
('G9_S10_03','L4','G9_P10','Intervals from graph','Определение промежутков по графику','По графику определите промежутки возрастания и убывания',3,'analyze',9,9,
 'По графику определите промежутки возрастания и убывания','Чтение графика функции','High (Level C)',NULL);

-- ─── П.11: Чётность и нечётность функции (3 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G9_S11_01','L4','G9_P11','Check evenness','Проверка чётности','Является ли функция y = x² чётной',1,'apply',9,9,
 'Является ли функция y = x² чётной','Проверка условия f(−x) = f(x)','Medium (Level B)',NULL),
('G9_S11_02','L4','G9_P11','Check oddness','Проверка нечётности','Является ли функция y = x³ нечётной',2,'apply',9,9,
 'Является ли функция y = x³ нечётной','Проверка условия f(−x) = −f(x)','Medium (Level B)',NULL),
('G9_S11_03','L4','G9_P11','Neither even nor odd','Ни чётная, ни нечётная','Определите, является ли функция y = x² + x чётной или нечётной',3,'analyze',9,9,
 'Определите, является ли функция y = x² + x чётной или нечётной','Проверка обоих условий','High (Level C)',NULL);

-- ─── П.12: Неравенства и уравнения с участием степени (4 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G9_S12_01','L4','G9_P12','Compare powers','Сравнение степеней','Сравните 2⁵ и 3³',1,'apply',9,9,
 'Сравните 2⁵ и 3³','Вычисление и сравнение значений степеней','Medium (Level B)',NULL),
('G9_S12_02','L4','G9_P12','Solve simple exponential equation','Решение простого показательного уравнения','Решите уравнение 2ˣ = 8',2,'apply',9,9,
 'Решите уравнение 2ˣ = 8','Представление правой части в виде степени основания','Medium (Level B)',NULL),
('G9_S12_03','L4','G9_P12','Solve exponential inequality','Решение показательного неравенства','Решите неравенство 3ˣ > 9',3,'analyze',9,9,
 'Решите неравенство 3ˣ > 9','Переход к сравнению показателей','High (Level C)',NULL),
('G9_S12_04','L4','G9_P12','Exponential with substitution','Показательное уравнение с заменой','Решите уравнение 4ˣ − 3 · 2ˣ + 2 = 0',4,'analyze',9,9,
 'Решите уравнение 4ˣ − 3 · 2ˣ + 2 = 0','Замена переменной t = 2ˣ','High (Level C)',NULL);

-- ─── П.13: Решение простейших систем уравнений 2-й степени (5 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G9_S13_01','L4','G9_P13','Simple system by substitution','Простая система подстановкой','Решите систему y = x², x + y = 2',1,'apply',9,9,
 'Решите систему y = x², x + y = 2','Подстановка выражения в уравнение','Medium (Level B)',NULL),
('G9_S13_02','L4','G9_P13','Linear and quadratic','Линейное и квадратное уравнение','Решите систему y = x + 1, y = x²',2,'analyze',9,9,
 'Решите систему y = x + 1, y = x²','Приравнивание двух выражений','High (Level C)',NULL),
('G9_S13_03','L4','G9_P13','Both equations quadratic','Обе уравнения квадратные','Решите систему x² + y² = 25, x − y = 1',3,'analyze',9,9,
 'Решите систему x² + y² = 25, x − y = 1','Выражение переменной и подстановка','High (Level C)',NULL),
('G9_S13_04','L4','G9_P13','Circle and line','Окружность и прямая','Найдите точки пересечения окружности x² + y² = 10 и прямой y = x + 2',4,'analyze',9,9,
 'Найдите точки пересечения окружности x² + y² = 10 и прямой y = x + 2','Решение системы из уравнения окружности и прямой','High (Level C)',NULL),
('G9_S13_05','L4','G9_P13','Select real solutions','Отбор действительных решений','Решите систему xy = 6, x + y = 5',5,'apply',9,9,
 'Решите систему xy = 6, x + y = 5','Составление квадратного уравнения и проверка решений','Medium (Level B)',NULL);

-- ─── П.14: Различные способы решения систем уравнений (5 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G9_S14_01','L4','G9_P14','Elimination method','Метод исключения','Решите систему x² − y² = 7, x − y = 1',1,'analyze',9,9,
 'Решите систему x² − y² = 7, x − y = 1','Использование разности квадратов для исключения','High (Level C)',NULL),
('G9_S14_02','L4','G9_P14','Introduce new variable','Введение новой переменной','Решите систему x + y = 5, xy = 6',2,'analyze',9,9,
 'Решите систему x + y = 5, xy = 6','Сведение к квадратному уравнению через t','High (Level C)',NULL),
('G9_S14_03','L4','G9_P14','Graphical method','Графический метод','Решите систему y = x², y = 2x графически',3,'apply',9,9,
 'Решите систему y = x², y = 2x графически','Нахождение точек пересечения графиков','Medium (Level B)',NULL),
('G9_S14_04','L4','G9_P14','Three unknowns','Система с тремя переменными','Решите систему x + y + z = 6, x − y = 2, y + z = 4',4,'analyze',9,9,
 'Решите систему x + y + z = 6, x − y = 2, y + z = 4','Последовательное исключение переменных','High (Level C)',NULL),
('G9_S14_05','L4','G9_P14','Symmetric system','Симметричная система','Решите систему x + y = 7, x² + y² = 25',5,'analyze',9,9,
 'Решите систему x + y = 7, x² + y² = 25','Использование (x + y)² = x² + 2xy + y²','High (Level C)',NULL);

-- ─── П.15: Системы неравенств 2-й степени (5 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G9_S15_01','L4','G9_P15','Solve system of quadratic inequalities','Решение системы квадратных неравенств','Решите систему x² − 4 > 0, x² − 9 < 0',1,'analyze',9,9,
 'Решите систему x² − 4 > 0, x² − 9 < 0','Нахождение пересечения двух множеств решений','High (Level C)',NULL),
('G9_S15_02','L4','G9_P15','Linear and quadratic inequality','Линейное и квадратное неравенство','Решите систему 2x − 1 > 0, x² − 4x + 3 < 0',2,'analyze',9,9,
 'Решите систему 2x − 1 > 0, x² − 4x + 3 < 0','Решение каждого неравенства и пересечение','High (Level C)',NULL),
('G9_S15_03','L4','G9_P15','Graph both inequalities','Графическое решение системы','Решите систему неравенств графически: y > x², y < x + 2',3,'analyze',9,9,
 'Решите систему неравенств графически: y > x², y < x + 2','Нахождение области пересечения на графике','High (Level C)',NULL),
('G9_S15_04','L4','G9_P15','System with modulus','Система с модулем','Решите систему |x| < 3, x² − 1 > 0',4,'analyze',9,9,
 'Решите систему |x| < 3, x² − 1 > 0','Раскрытие модуля и пересечение решений','High (Level C)',NULL),
('G9_S15_05','L4','G9_P15','Determine solution interval','Определение числового промежутка','Запишите множество решений в виде объединения промежутков',5,'apply',9,9,
 'Запишите множество решений в виде объединения промежутков','Переход от графического решения к интервальной записи','Medium (Level B)',NULL);

-- ─── П.16: Доказательство простейших неравенств (5 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G9_S16_01','L4','G9_P16','Prove using complete square','Доказательство через полный квадрат','Докажите, что x² + 4x + 5 > 0 для всех x',1,'analyze',9,9,
 'Докажите, что x² + 4x + 5 > 0 для всех x','Выделение полного квадрата','High (Level C)','x²+4x+5=(x+2)²+1'),
('G9_S16_02','L4','G9_P16','Prove sum of squares','Доказательство через сумму квадратов','Докажите, что a² + b² ≥ 2ab',2,'analyze',9,9,
 'Докажите, что a² + b² ≥ 2ab','Использование неравенства (a − b)² ≥ 0','High (Level C)','(a−b)²≥0'),
('G9_S16_03','L4','G9_P16','Prove AM-GM','Доказательство неравенства о средних','Докажите, что (a + b)/2 ≥ √(ab) для a, b > 0',3,'analyze',9,9,
 'Докажите, что (a + b)/2 ≥ √(ab) для a, b > 0','Применение неравенства о средних','High (Level C)','(a+b)/2≥√(ab)'),
('G9_S16_04','L4','G9_P16','Prove with Cauchy inequality','Доказательство методом оценки','Докажите, что если a + b = 1, то a² + b² ≥ 1/2',4,'analyze',9,9,
 'Докажите, что если a + b = 1, то a² + b² ≥ 1/2','Применение метода фиксированной суммы','High (Level C)',NULL),
('G9_S16_05','L4','G9_P16','Prove expression positive','Доказательство положительности выражения','Докажите, что x⁴ + x² + 1 > 0 для всех x',5,'apply',9,9,
 'Докажите, что x⁴ + x² + 1 > 0 для всех x','Анализ выражения как суммы квадратов','Medium (Level B)',NULL);

-- ─── П.17: Радианная мера угла (5 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G9_S17_01','L4','G9_P17','Convert degrees to radians','Перевод градусов в радианы','Переведите 180° в радианы',1,'recall',9,9,
 'Переведите 180° в радианы','Применение соотношения 180° = π','Low (Level A)','φ(рад)=φ(°)·π/180'),
('G9_S17_02','L4','G9_P17','Convert radians to degrees','Перевод радианов в градусы','Переведите π/6 в градусы',2,'apply',9,9,
 'Переведите π/6 в градусы','Обратный перевод','Medium (Level B)',NULL),
('G9_S17_03','L4','G9_P17','Standard angles','Перевод стандартных углов','Переведите 90°, 60°, 45°, 30° в радианы',3,'apply',9,9,
 'Переведите 90°, 60°, 45°, 30° в радианы','Знание стандартных значений','Medium (Level B)',NULL),
('G9_S17_04','L4','G9_P17','Angle more than 360','Работа с углами больше 360°','Переведите 720° в радианы',4,'apply',9,9,
 'Переведите 720° в радианы','Корректная работа с большими углами','Medium (Level B)',NULL),
('G9_S17_05','L4','G9_P17','Arc length','Длина дуги','Найдите длину дуги с радиусом 5 и углом π/3',5,'analyze',9,9,
 'Найдите длину дуги с радиусом 5 и углом π/3','Применение формулы длины дуги','High (Level C)','l=Rφ');

-- ─── П.18: Поворот точки вокруг начала координат (5 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G9_S18_01','L4','G9_P18','90 degree rotation','Поворот на 90°','Найдите координаты точки (1; 0) после поворота на 90°',1,'recall',9,9,
 'Найдите координаты точки (1; 0) после поворота на 90°','Понимание поворота точки','Low (Level A)',NULL),
('G9_S18_02','L4','G9_P18','180 degree rotation','Поворот на 180°','Найдите координаты точки (3; 4) после поворота на 180°',2,'apply',9,9,
 'Найдите координаты точки (3; 4) после поворота на 180°','Изменение знаков координат','Medium (Level B)',NULL),
('G9_S18_03','L4','G9_P18','Unit circle','Работа с единичной окружностью','Укажите координаты точки на единичной окружности для угла π/2',3,'apply',9,9,
 'Укажите координаты точки на единичной окружности для угла π/2','Определение положения точки на окружности','Medium (Level B)',NULL),
('G9_S18_04','L4','G9_P18','Arbitrary angle','Поворот на произвольный угол','Найдите координаты точки (1; 0) после поворота на 2π/3',4,'analyze',9,9,
 'Найдите координаты точки (1; 0) после поворота на 2π/3','Вычисление координат через cos и sin','High (Level C)',NULL),
('G9_S18_05','L4','G9_P18','Negative angle','Поворот на отрицательный угол','Найдите координаты точки после поворота на −π/4',5,'analyze',9,9,
 'Найдите координаты точки после поворота на −π/4','Понимание поворота по часовой стрелке','High (Level C)',NULL);

-- ─── П.19: Определение sin, cos, tg, ctg (5 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G9_S19_01','L4','G9_P19','Definition of sin and cos','Определение sin и cos','Назовите sin и cos для точки на единичной окружности с координатами (√3/2; 1/2)',1,'recall',9,9,
 'Назовите sin и cos для точки на единичной окружности с координатами (√3/2; 1/2)','Связь координат с синусом и косинусом','Low (Level A)',NULL),
('G9_S19_02','L4','G9_P19','Values at standard angles','Значения в стандартных углах','Найдите sin 30°, cos 60°, tg 45°',2,'apply',9,9,
 'Найдите sin 30°, cos 60°, tg 45°','Знание табличных значений','Medium (Level B)',NULL),
('G9_S19_03','L4','G9_P19','Definition of tan and cot','Определение tg и ctg','Найдите tg α и ctg α, если sin α = 3/5, cos α = 4/5',3,'apply',9,9,
 'Найдите tg α и ctg α, если sin α = 3/5, cos α = 4/5','Применение определений tg = sin/cos, ctg = cos/sin','Medium (Level B)','tg α=sin α/cos α'),
('G9_S19_04','L4','G9_P19','Compute all functions','Вычисление всех тригонометрических функций','Найдите sin, cos, tg, ctg для угла π/4',4,'apply',9,9,
 'Найдите sin, cos, tg, ctg для угла π/4','Полный набор значений для стандартного угла','Medium (Level B)',NULL),
('G9_S19_05','L4','G9_P19','Non-standard angle','Работа с нестандартным углом','Если точка на окружности имеет координаты (−1/2; √3/2), найдите угол',5,'analyze',9,9,
 'Если точка на окружности имеет координаты (−1/2; √3/2), найдите угол','Определение угла по координатам','High (Level C)',NULL);

-- ─── П.20: Знаки sin, cos, tg по четвертям (5 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G9_S20_01','L4','G9_P20','Signs by quadrant','Знаки по четвертям','Определите знак sin 150°',1,'apply',9,9,
 'Определите знак sin 150°','Знание знаков sin и cos в каждой четверти','Medium (Level B)',NULL),
('G9_S20_02','L4','G9_P20','Determine quadrant','Определение четверти','В какой четверти находится угол 200°',2,'apply',9,9,
 'В какой четверти находится угол 200°','Определение четверти по градусной мере','Medium (Level B)',NULL),
('G9_S20_03','L4','G9_P20','Sign of tan','Знак tg в четвертях','Определите знак tg 300°',3,'apply',9,9,
 'Определите знак tg 300°','Анализ знака отношения sin/cos','Medium (Level B)',NULL),
('G9_S20_04','L4','G9_P20','All signs for angle','Определение знаков всех функций','Определите знаки sin, cos, tg для угла 5π/4',4,'analyze',9,9,
 'Определите знаки sin, cos, tg для угла 5π/4','Комплексный анализ знаков в третьей четверти','High (Level C)',NULL),
('G9_S20_05','L4','G9_P20','Find quadrant from conditions','Нахождение четверти по условиям','В какой четверти sin α > 0 и cos α < 0',5,'analyze',9,9,
 'В какой четверти sin α > 0 и cos α < 0','Определение четверти по комбинации знаков','High (Level C)',NULL);

-- ─── П.21: Связь между sin, cos, tg, ctg (8 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G9_S21_01','L4','G9_P21','Fundamental identity','Основное тригонометрическое тождество','Найдите cos α, если sin α = 3/5 и α в первой четверти',1,'apply',9,9,
 'Найдите cos α, если sin α = 3/5 и α в первой четверти','Применение sin²α + cos²α = 1','Medium (Level B)','sin²α+cos²α=1'),
('G9_S21_02','L4','G9_P21','Express tan through sin cos','Выражение tg через sin и cos','Найдите tg α, если sin α = 4/5, cos α = 3/5',2,'apply',9,9,
 'Найдите tg α, если sin α = 4/5, cos α = 3/5','Применение tg α = sin α / cos α','Medium (Level B)','tg α=sin α/cos α'),
('G9_S21_03','L4','G9_P21','tan times cot equals 1','Произведение tg и ctg','Вычислите tg α · ctg α',3,'recall',9,9,
 'Вычислите tg α · ctg α','Применение тождества tg α · ctg α = 1','Low (Level A)','tg α·ctg α=1'),
('G9_S21_04','L4','G9_P21','1 plus tan squared','Тождество 1 + tg²α','Найдите cos α, если tg α = 2',4,'analyze',9,9,
 'Найдите cos α, если tg α = 2','Применение тождества 1 + tg²α = 1/cos²α','High (Level C)','1+tg²α=1/cos²α'),
('G9_S21_05','L4','G9_P21','1 plus cot squared','Тождество 1 + ctg²α','Найдите sin α, если ctg α = 3',5,'analyze',9,9,
 'Найдите sin α, если ctg α = 3','Применение тождества 1 + ctg²α = 1/sin²α','High (Level C)','1+ctg²α=1/sin²α'),
('G9_S21_06','L4','G9_P21','Chain calculation','Цепочка вычислений','Если sin α = 5/13, найдите cos α, tg α, ctg α',6,'analyze',9,9,
 'Если sin α = 5/13, найдите cos α, tg α, ctg α','Последовательное применение нескольких тождеств','High (Level C)',NULL),
('G9_S21_07','L4','G9_P21','Simplify expression','Упрощение тригонометрического выражения','Упростите sin²α + cos²α + tg α · ctg α',7,'apply',9,9,
 'Упростите sin²α + cos²α + tg α · ctg α','Комбинирование основных тождеств','Medium (Level B)',NULL),
('G9_S21_08','L4','G9_P21','Prove identity','Доказательство тождества','Докажите, что (1 − sin²α)(1 + tg²α) = 1',8,'analyze',9,9,
 'Докажите, что (1 − sin²α)(1 + tg²α) = 1','Преобразование с использованием нескольких тождеств','High (Level C)',NULL);

-- ─── П.22: Тригонометрические тождества (8 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G9_S22_01','L4','G9_P22','Verify identity','Проверка тождества','Проверьте, что sin²30° + cos²30° = 1',1,'apply',9,9,
 'Проверьте, что sin²30° + cos²30° = 1','Подстановка табличных значений','Medium (Level B)',NULL),
('G9_S22_02','L4','G9_P22','Simplify to constant','Упрощение до числа','Упростите sin²α/(1 − cos²α)',2,'apply',9,9,
 'Упростите sin²α/(1 − cos²α)','Использование sin²α = 1 − cos²α','Medium (Level B)',NULL),
('G9_S22_03','L4','G9_P22','Express one through another','Выражение одной функции через другую','Выразите sin α через cos α',3,'apply',9,9,
 'Выразите sin α через cos α','Применение основного тождества','Medium (Level B)','sin α=±√(1−cos²α)'),
('G9_S22_04','L4','G9_P22','Complex identity','Доказательство сложного тождества','Докажите, что cos⁴α − sin⁴α = cos²α − sin²α',4,'analyze',9,9,
 'Докажите, что cos⁴α − sin⁴α = cos²α − sin²α','Применение формулы разности квадратов к тригонометрии','High (Level C)',NULL),
('G9_S22_05','L4','G9_P22','Transform fraction','Преобразование тригонометрической дроби','Упростите (1 − cos²α)/sin α',5,'analyze',9,9,
 'Упростите (1 − cos²α)/sin α','Замена 1 − cos²α на sin²α','High (Level C)',NULL),
('G9_S22_06','L4','G9_P22','Prove complex identity','Доказательство с несколькими шагами','Докажите, что (sin α + cos α)² = 1 + 2sin α cos α',6,'analyze',9,9,
 'Докажите, что (sin α + cos α)² = 1 + 2sin α cos α','Раскрытие квадрата и применение тождества','High (Level C)',NULL),
('G9_S22_07','L4','G9_P22','Compute with identity','Вычисление значения через тождество','Вычислите sin²α + sin²α · tg²α, если cos α = 1/3',7,'analyze',9,9,
 'Вычислите sin²α + sin²α · tg²α, если cos α = 1/3','Комбинированное преобразование','High (Level C)',NULL),
('G9_S22_08','L4','G9_P22','Multi-step simplification','Многошаговое упрощение','Упростите tg²α − sin²α/(tg²α · sin²α)',8,'analyze',9,9,
 'Упростите tg²α − sin²α/(tg²α · sin²α)','Цепочка тождественных преобразований','High (Level C)',NULL);

-- ─── П.23: sin, cos, tg углов α и −α (5 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G9_S23_01','L4','G9_P23','sin of negative angle','Синус отрицательного угла','Найдите sin(−30°)',1,'apply',9,9,
 'Найдите sin(−30°)','Применение sin(−α) = −sin α','Medium (Level B)','sin(−α)=−sin α'),
('G9_S23_02','L4','G9_P23','cos of negative angle','Косинус отрицательного угла','Найдите cos(−60°)',2,'apply',9,9,
 'Найдите cos(−60°)','Применение cos(−α) = cos α','Medium (Level B)','cos(−α)=cos α'),
('G9_S23_03','L4','G9_P23','tan of negative angle','Тангенс отрицательного угла','Найдите tg(−45°)',3,'apply',9,9,
 'Найдите tg(−45°)','Применение tg(−α) = −tg α','Medium (Level B)','tg(−α)=−tg α'),
('G9_S23_04','L4','G9_P23','Simplify with negative angle','Упрощение с отрицательным углом','Упростите sin(−α) + sin α',4,'apply',9,9,
 'Упростите sin(−α) + sin α','Применение свойств чётности/нечётности','Medium (Level B)',NULL),
('G9_S23_05','L4','G9_P23','Complex expression with negatives','Сложное выражение с отрицательными углами','Упростите cos(−α) · tg(−α) + sin α',5,'analyze',9,9,
 'Упростите cos(−α) · tg(−α) + sin α','Комбинирование нескольких правил','High (Level C)',NULL);

-- ─── П.24: Формулы сложения (5 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G9_S24_01','L4','G9_P24','sin of sum','Синус суммы углов','Найдите sin(45° + 30°)',1,'apply',9,9,
 'Найдите sin(45° + 30°)','Применение формулы sin(α + β)','Medium (Level B)','sin(α+β)=sinαcosβ+cosαsinβ'),
('G9_S24_02','L4','G9_P24','cos of sum','Косинус суммы углов','Найдите cos(60° + 45°)',2,'apply',9,9,
 'Найдите cos(60° + 45°)','Применение формулы cos(α + β)','Medium (Level B)','cos(α+β)=cosαcosβ−sinαsinβ'),
('G9_S24_03','L4','G9_P24','sin of difference','Синус разности углов','Найдите sin(90° − 30°)',3,'apply',9,9,
 'Найдите sin(90° − 30°)','Применение формулы sin(α − β)','Medium (Level B)','sin(α−β)=sinαcosβ−cosαsinβ'),
('G9_S24_04','L4','G9_P24','Compute non-standard angle','Вычисление нестандартного угла','Найдите cos 15° через формулу cos(45° − 30°)',4,'analyze',9,9,
 'Найдите cos 15° через формулу cos(45° − 30°)','Представление угла как разности стандартных','High (Level C)',NULL),
('G9_S24_05','L4','G9_P24','Prove with addition formulas','Доказательство через формулы сложения','Докажите, что sin(90° − α) = cos α',5,'analyze',9,9,
 'Докажите, что sin(90° − α) = cos α','Применение формулы sin(α − β) к стандартным углам','High (Level C)',NULL);

-- ─── П.25: Синус и косинус двойного угла (5 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G9_S25_01','L4','G9_P25','sin of double angle','Синус двойного угла','Найдите sin 2α, если sin α = 3/5, cos α = 4/5',1,'apply',9,9,
 'Найдите sin 2α, если sin α = 3/5, cos α = 4/5','Применение формулы sin 2α = 2sin α cos α','Medium (Level B)','sin 2α=2sin α cos α'),
('G9_S25_02','L4','G9_P25','cos of double angle','Косинус двойного угла','Найдите cos 2α, если cos α = 1/2',2,'apply',9,9,
 'Найдите cos 2α, если cos α = 1/2','Применение формулы cos 2α = 2cos²α − 1','Medium (Level B)','cos 2α=cos²α−sin²α'),
('G9_S25_03','L4','G9_P25','Alternative cos formulas','Альтернативные формулы cos 2α','Выразите cos 2α через sin α',3,'apply',9,9,
 'Выразите cos 2α через sin α','Применение формулы cos 2α = 1 − 2sin²α','Medium (Level B)','cos 2α=1−2sin²α'),
('G9_S25_04','L4','G9_P25','Compute double angle value','Вычисление значения двойного угла','Вычислите sin 60° через sin 2·30°',4,'analyze',9,9,
 'Вычислите sin 60° через sin 2·30°','Проверка формулы на стандартных углах','High (Level C)',NULL),
('G9_S25_05','L4','G9_P25','Simplify with double angle','Упрощение через двойной угол','Упростите 2sin α cos α/(cos²α − sin²α)',5,'analyze',9,9,
 'Упростите 2sin α cos α/(cos²α − sin²α)','Замена на sin 2α / cos 2α = tg 2α','High (Level C)',NULL);

-- ─── П.26: Формулы приведения (17 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G9_S26_01','L4','G9_P26','Reduce angle > 360','Приведение углов больше 360°','Найдите sin 390°',1,'apply',9,9,
 'Найдите sin 390°','Вычитание полного оборота: 390° = 360° + 30°','Medium (Level B)',NULL),
('G9_S26_02','L4','G9_P26','Reduce radian angle','Приведение углов в радианах','Найдите cos(5π/2)',2,'apply',9,9,
 'Найдите cos(5π/2)','Вычитание 2π: 5π/2 = 2π + π/2','Medium (Level B)',NULL),
('G9_S26_03','L4','G9_P26','Angles kπ','Работа с углами вида kπ','Найдите sin π, cos 2π, sin 3π',3,'apply',9,9,
 'Найдите sin π, cos 2π, sin 3π','Знание значений sin и cos в кратных π точках','Medium (Level B)',NULL),
('G9_S26_04','L4','G9_P26','Reduction π−α','Приведение π − α','Упростите sin(π − α)',4,'apply',9,9,
 'Упростите sin(π − α)','Применение формулы sin(π − α) = sin α','Medium (Level B)','sin(π−α)=sin α'),
('G9_S26_05','L4','G9_P26','Reduction π/2−α','Приведение π/2 − α','Упростите cos(π/2 − α)',5,'apply',9,9,
 'Упростите cos(π/2 − α)','Применение формулы cos(π/2 − α) = sin α','Medium (Level B)','cos(π/2−α)=sin α'),
('G9_S26_06','L4','G9_P26','Negative angle reduction','Приведение отрицательного угла','Найдите cos(−π/3)',6,'apply',9,9,
 'Найдите cos(−π/3)','Применение чётности cos','Medium (Level B)',NULL),
('G9_S26_07','L4','G9_P26','Compute via standard angles','Вычисление через стандартные углы','Найдите sin(3π/4)',7,'analyze',9,9,
 'Найдите sin(3π/4)','Представление 3π/4 = π − π/4 и применение формулы приведения','High (Level C)',NULL),
('G9_S26_08','L4','G9_P26','Combined expressions','Комбинированные выражения','Вычислите sin(π − α) + cos(π/2 + α)',8,'analyze',9,9,
 'Вычислите sin(π − α) + cos(π/2 + α)','Последовательное применение формул приведения','High (Level C)','cos(π/2+α)=−sin α'),
('G9_S26_09','L4','G9_P26','π and negative angles','Работа с π и отрицательными углами','Упростите cos(π + α) + cos(−α)',9,'analyze',9,9,
 'Упростите cos(π + α) + cos(−α)','Применение cos(π + α) = −cos α и cos(−α) = cos α','High (Level C)','cos(π+α)=−cos α'),
('G9_S26_10','L4','G9_P26','Simplify π−α expression','Упрощение выражений с (π − α)','Упростите sin(π − α) · cos(π − α)',10,'analyze',9,9,
 'Упростите sin(π − α) · cos(π − α)','Применение sin(π − α) = sin α, cos(π − α) = −cos α','High (Level C)',NULL),
('G9_S26_11','L4','G9_P26','Products of trig functions','Произведения тригонометрических функций','Упростите sin(π/2 − α) · tg(π − α)',11,'analyze',9,9,
 'Упростите sin(π/2 − α) · tg(π − α)','Приведение нескольких функций и умножение','High (Level C)',NULL),
('G9_S26_12','L4','G9_P26','Fractional trig expressions','Дробные тригонометрические выражения','Упростите sin(π − α)/cos(π/2 − α)',12,'analyze',9,9,
 'Упростите sin(π − α)/cos(π/2 − α)','Приведение числителя и знаменателя отдельно','High (Level C)',NULL),
('G9_S26_13','L4','G9_P26','Reduce complex angles','Приведение сложных углов','Найдите sin(7π/6)',13,'analyze',9,9,
 'Найдите sin(7π/6)','Представление как π + π/6','High (Level C)',NULL),
('G9_S26_14','L4','G9_P26','Simplify tg and ctg','Упрощение выражений с tg и ctg','Упростите tg(π − α) + ctg(π/2 − α)',14,'analyze',9,9,
 'Упростите tg(π − α) + ctg(π/2 − α)','Применение формул приведения для tg и ctg','High (Level C)','tg(π−α)=−tg α'),
('G9_S26_15','L4','G9_P26','Prove identity using reduction','Доказательство тождества через приведение','Докажите, что sin(π/2 + α) = cos α',15,'analyze',9,9,
 'Докажите, что sin(π/2 + α) = cos α','Проверка через формулу сложения','High (Level C)','sin(π/2+α)=cos α'),
('G9_S26_16','L4','G9_P26','Solve equation with reduction','Решение уравнения с приведением','Решите уравнение sin(π − x) = 1/2',16,'analyze',9,9,
 'Решите уравнение sin(π − x) = 1/2','Приведение к sin x = 1/2','High (Level C)',NULL),
('G9_S26_17','L4','G9_P26','Solve through basic values','Решение через базовые значения','Решите уравнение cos(π/2 − x) = √3/2',17,'analyze',9,9,
 'Решите уравнение cos(π/2 − x) = √3/2','Приведение к sin x = √3/2','High (Level C)',NULL);

-- ─── П.27: Сумма и разность синусов и косинусов (19 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G9_S27_01','L4','G9_P27','Sum of sines formula','Формула суммы синусов','Представьте sin 40° + sin 20° в виде произведения',1,'apply',9,9,
 'Представьте sin 40° + sin 20° в виде произведения','Применение формулы sinα+sinβ=2sin((α+β)/2)cos((α−β)/2)','Medium (Level B)','sinα+sinβ=2sin((α+β)/2)cos((α−β)/2)'),
('G9_S27_02','L4','G9_P27','Difference of cosines','Формула разности косинусов','Представьте cos 30° − cos 70° в виде произведения',2,'apply',9,9,
 'Представьте cos 30° − cos 70° в виде произведения','Применение формулы cosα−cosβ','Medium (Level B)','cosα−cosβ=−2sin((α+β)/2)sin((α−β)/2)'),
('G9_S27_03','L4','G9_P27','Squares of trig expressions','Квадраты тригонометрических выражений','Упростите sin²α − cos²α',3,'apply',9,9,
 'Упростите sin²α − cos²α','Связь с cos 2α','Medium (Level B)',NULL),
('G9_S27_04','L4','G9_P27','Difference of cosines transform','Преобразование разности косинусов','Упростите cos α − cos 3α через произведение',4,'analyze',9,9,
 'Упростите cos α − cos 3α через произведение','Применение формулы разности косинусов','High (Level C)',NULL),
('G9_S27_05','L4','G9_P27','Compute via sum formula','Вычисление через формулу суммы','Вычислите sin 75° + sin 15°',5,'analyze',9,9,
 'Вычислите sin 75° + sin 15°','Применение формулы суммы синусов','High (Level C)',NULL),
('G9_S27_06','L4','G9_P27','Difference of sines','Разность синусов','Вычислите sin 50° − sin 10°',6,'analyze',9,9,
 'Вычислите sin 50° − sin 10°','Применение формулы sinα−sinβ','High (Level C)','sinα−sinβ=2cos((α+β)/2)sin((α−β)/2)'),
('G9_S27_07','L4','G9_P27','Radian angles in sum','Работа с углами в радианах','Представьте sin(π/3) + sin(π/6) в виде произведения',7,'analyze',9,9,
 'Представьте sin(π/3) + sin(π/6) в виде произведения','Применение формул к радианным углам','High (Level C)',NULL),
('G9_S27_08','L4','G9_P27','Sum to product','Представление суммы в виде произведения','Представьте sin 3α + sin α в виде произведения',8,'analyze',9,9,
 'Представьте sin 3α + sin α в виде произведения','Применение формулы с буквенными углами','High (Level C)',NULL),
('G9_S27_09','L4','G9_P27','cos sum to product','Представление суммы cos в виде произведения','Представьте cos 5α + cos 3α в виде произведения',9,'analyze',9,9,
 'Представьте cos 5α + cos 3α в виде произведения','Применение формулы cosα+cosβ=2cos((α+β)/2)cos((α−β)/2)','High (Level C)','cosα+cosβ=2cos((α+β)/2)cos((α−β)/2)'),
('G9_S27_10','L4','G9_P27','Prove identity via sum-product','Доказательство тождества','Докажите, что sin 3α + sin α = 2sin 2α cos α',10,'analyze',9,9,
 'Докажите, что sin 3α + sin α = 2sin 2α cos α','Преобразование левой части формулой суммы','High (Level C)',NULL),
('G9_S27_11','L4','G9_P27','Prove via difference','Доказательство через разность','Докажите, что cos α − cos 3α = 2sin 2α sin α',11,'analyze',9,9,
 'Докажите, что cos α − cos 3α = 2sin 2α sin α','Применение формулы разности косинусов','High (Level C)',NULL),
('G9_S27_12','L4','G9_P27','Simplify complex fractions','Упрощение сложных дробей','Упростите (sin 3α + sin α)/(cos 3α + cos α)',12,'analyze',9,9,
 'Упростите (sin 3α + sin α)/(cos 3α + cos α)','Применение формул суммы к числителю и знаменателю','High (Level C)',NULL),
('G9_S27_13','L4','G9_P27','Multiple angles','Работа с несколькими углами','Упростите sin α + sin 2α + sin 3α',13,'analyze',9,9,
 'Упростите sin α + sin 2α + sin 3α','Группировка и применение формул','High (Level C)',NULL),
('G9_S27_14','L4','G9_P27','Prove complex trig identity','Доказательство сложного тождества','Докажите, что (sin 5α − sin 3α)/(cos 5α + cos 3α) = tg α',14,'analyze',9,9,
 'Докажите, что (sin 5α − sin 3α)/(cos 5α + cos 3α) = tg α','Применение формул разности синусов и суммы косинусов','High (Level C)',NULL),
('G9_S27_15','L4','G9_P27','Sum of multiple cosines','Сумма нескольких косинусов','Упростите cos α + cos 3α + cos 5α',15,'analyze',9,9,
 'Упростите cos α + cos 3α + cos 5α','Последовательная группировка и преобразование','High (Level C)',NULL),
('G9_S27_16','L4','G9_P27','Long sum of sines','Длинная сумма синусов','Упростите sin α + sin 3α + sin 5α',16,'analyze',9,9,
 'Упростите sin α + sin 3α + sin 5α','Использование пар и формул суммы','High (Level C)',NULL),
('G9_S27_17','L4','G9_P27','Product to sum','Представление произведения в сумму','Представьте 2sin 3α cos α в виде суммы',17,'analyze',9,9,
 'Представьте 2sin 3α cos α в виде суммы','Обратное применение формул','High (Level C)',NULL),
('G9_S27_18','L4','G9_P27','Expressions 1±cos 1±sin','Выражения вида 1 ± cos α, 1 ± sin α','Упростите 1 − cos 2α',18,'analyze',9,9,
 'Упростите 1 − cos 2α','Применение формулы cos 2α = 1 − 2sin²α','High (Level C)','1−cos 2α=2sin²α'),
('G9_S27_19','L4','G9_P27','Mixed simplification','Упрощение смешанных выражений','Упростите (sin α + sin β)/(cos α + cos β)',19,'analyze',9,9,
 'Упростите (sin α + sin β)/(cos α + cos β)','Применение формул суммы к обеим частям','High (Level C)',NULL);

-- ─── П.28: Числовые последовательности (5 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G9_S28_01','L4','G9_P28','Write sequence by formula','Запись членов последовательности','Напишите первые 5 членов последовательности aₙ = 2n − 1',1,'recall',9,9,
 'Напишите первые 5 членов последовательности aₙ = 2n − 1','Подстановка значений n','Low (Level A)',NULL),
('G9_S28_02','L4','G9_P28','Find formula','Нахождение формулы n-го члена','Найдите формулу n-го члена последовательности 2, 4, 6, 8, ...',2,'apply',9,9,
 'Найдите формулу n-го члена последовательности 2, 4, 6, 8, ...','Определение закономерности','Medium (Level B)',NULL),
('G9_S28_03','L4','G9_P28','Recursive sequence','Рекуррентная последовательность','Найдите первые 4 члена, если a₁ = 1, aₙ₊₁ = aₙ + 3',3,'apply',9,9,
 'Найдите первые 4 члена, если a₁ = 1, aₙ₊₁ = aₙ + 3','Последовательное вычисление членов','Medium (Level B)',NULL),
('G9_S28_04','L4','G9_P28','Check if increasing','Проверка монотонности','Является ли последовательность aₙ = n² возрастающей',4,'apply',9,9,
 'Является ли последовательность aₙ = n² возрастающей','Сравнение последовательных членов','Medium (Level B)',NULL),
('G9_S28_05','L4','G9_P28','Find specific term','Нахождение конкретного члена','Найдите a₁₀ для последовательности aₙ = 3n + 2',5,'analyze',9,9,
 'Найдите a₁₀ для последовательности aₙ = 3n + 2','Подстановка конкретного значения n','High (Level C)',NULL);

-- ─── П.29: Арифметическая прогрессия (5 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G9_S29_01','L4','G9_P29','Identify AP','Распознавание арифметической прогрессии','Является ли последовательность 3, 7, 11, 15 арифметической прогрессией',1,'recall',9,9,
 'Является ли последовательность 3, 7, 11, 15 арифметической прогрессией','Проверка постоянства разности','Low (Level A)',NULL),
('G9_S29_02','L4','G9_P29','Find common difference','Нахождение разности прогрессии','Найдите разность арифметической прогрессии 5, 8, 11, 14',2,'apply',9,9,
 'Найдите разность арифметической прогрессии 5, 8, 11, 14','Вычисление d = aₙ₊₁ − aₙ','Medium (Level B)','d=aₙ₊₁−aₙ'),
('G9_S29_03','L4','G9_P29','Find nth term','Нахождение n-го члена','Найдите a₂₀, если a₁ = 3, d = 4',3,'apply',9,9,
 'Найдите a₂₀, если a₁ = 3, d = 4','Применение формулы aₙ = a₁ + (n − 1)d','Medium (Level B)','aₙ=a₁+(n−1)d'),
('G9_S29_04','L4','G9_P29','Find a1 from conditions','Нахождение первого члена','Найдите a₁, если a₅ = 23, d = 5',4,'analyze',9,9,
 'Найдите a₁, если a₅ = 23, d = 5','Выражение a₁ из формулы','High (Level C)',NULL),
('G9_S29_05','L4','G9_P29','Find number of terms','Нахождение количества членов','Сколько членов в прогрессии 2, 5, 8, ..., 59',5,'analyze',9,9,
 'Сколько членов в прогрессии 2, 5, 8, ..., 59','Решение уравнения aₙ = a₁ + (n − 1)d','High (Level C)',NULL);

-- ─── П.30: Сумма n первых членов арифметической прогрессии (5 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G9_S30_01','L4','G9_P30','Sum by formula','Нахождение суммы по формуле','Найдите сумму первых 10 членов АП, если a₁ = 2, d = 3',1,'apply',9,9,
 'Найдите сумму первых 10 членов АП, если a₁ = 2, d = 3','Применение формулы суммы','Medium (Level B)','Sₙ=(2a₁+(n−1)d)·n/2'),
('G9_S30_02','L4','G9_P30','Sum with last term','Сумма через первый и последний члены','Найдите сумму первых 20 членов, если a₁ = 1, a₂₀ = 39',2,'apply',9,9,
 'Найдите сумму первых 20 членов, если a₁ = 1, a₂₀ = 39','Применение формулы Sₙ = (a₁ + aₙ)n/2','Medium (Level B)','Sₙ=(a₁+aₙ)·n/2'),
('G9_S30_03','L4','G9_P30','Sum of natural numbers','Сумма натуральных чисел','Найдите сумму первых 100 натуральных чисел',3,'analyze',9,9,
 'Найдите сумму первых 100 натуральных чисел','Определение АП и применение формулы','High (Level C)',NULL),
('G9_S30_04','L4','G9_P30','Find n from sum','Нахождение n по сумме','Сумма первых n членов АП a₁ = 5, d = 3 равна 155. Найдите n',4,'analyze',9,9,
 'Сумма первых n членов АП a₁ = 5, d = 3 равна 155. Найдите n','Составление и решение квадратного уравнения','High (Level C)',NULL),
('G9_S30_05','L4','G9_P30','Word problem on AP sum','Текстовая задача на сумму АП','В первый день выложили 10 кирпичей, каждый день на 5 больше. За сколько дней выложат 200',5,'analyze',9,9,
 'В первый день выложили 10 кирпичей, каждый день на 5 больше. За сколько дней выложат 200','Моделирование ситуации через АП','High (Level C)',NULL);

-- ─── П.31: Геометрическая прогрессия (5 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G9_S31_01','L4','G9_P31','Identify GP','Распознавание геометрической прогрессии','Является ли последовательность 2, 6, 18, 54 геометрической прогрессией',1,'recall',9,9,
 'Является ли последовательность 2, 6, 18, 54 геометрической прогрессией','Проверка постоянства отношения','Low (Level A)',NULL),
('G9_S31_02','L4','G9_P31','Find common ratio','Нахождение знаменателя прогрессии','Найдите знаменатель ГП 3, 12, 48, 192',2,'apply',9,9,
 'Найдите знаменатель ГП 3, 12, 48, 192','Вычисление q = bₙ₊₁/bₙ','Medium (Level B)','q=bₙ₊₁/bₙ'),
('G9_S31_03','L4','G9_P31','Find nth term GP','Нахождение n-го члена ГП','Найдите b₆, если b₁ = 2, q = 3',3,'apply',9,9,
 'Найдите b₆, если b₁ = 2, q = 3','Применение формулы bₙ = b₁ · qⁿ⁻¹','Medium (Level B)','bₙ=b₁·qⁿ⁻¹'),
('G9_S31_04','L4','G9_P31','Find b1 from conditions','Нахождение первого члена ГП','Найдите b₁, если b₅ = 162, q = 3',4,'analyze',9,9,
 'Найдите b₁, если b₅ = 162, q = 3','Выражение b₁ из формулы','High (Level C)',NULL),
('G9_S31_05','L4','G9_P31','Decreasing GP','Убывающая ГП','Найдите b₅ для ГП 64, 32, 16, ...',5,'analyze',9,9,
 'Найдите b₅ для ГП 64, 32, 16, ...','Работа с q < 1','High (Level C)',NULL);

-- ─── П.32: Сумма n первых членов геометрической прогрессии (5 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G9_S32_01','L4','G9_P32','Sum of GP','Нахождение суммы ГП','Найдите сумму первых 5 членов ГП b₁ = 1, q = 2',1,'apply',9,9,
 'Найдите сумму первых 5 членов ГП b₁ = 1, q = 2','Применение формулы суммы','Medium (Level B)','Sₙ=b₁(qⁿ−1)/(q−1)'),
('G9_S32_02','L4','G9_P32','Sum with q<1','Сумма при q < 1','Найдите сумму первых 4 членов ГП b₁ = 81, q = 1/3',2,'apply',9,9,
 'Найдите сумму первых 4 членов ГП b₁ = 81, q = 1/3','Применение формулы с q < 1','Medium (Level B)',NULL),
('G9_S32_03','L4','G9_P32','Find n from GP sum','Нахождение n по сумме ГП','Сумма первых n членов ГП b₁ = 1, q = 3 равна 121. Найдите n',3,'analyze',9,9,
 'Сумма первых n членов ГП b₁ = 1, q = 3 равна 121. Найдите n','Решение показательного уравнения','High (Level C)',NULL),
('G9_S32_04','L4','G9_P32','Sum of powers of 2','Сумма степеней двойки','Найдите сумму 1 + 2 + 4 + ... + 2⁹',4,'analyze',9,9,
 'Найдите сумму 1 + 2 + 4 + ... + 2⁹','Определение b₁, q и n, применение формулы','High (Level C)',NULL),
('G9_S32_05','L4','G9_P32','Word problem on GP sum','Текстовая задача на сумму ГП','Бактерия делится надвое каждый час. Сколько бактерий за 10 часов',5,'analyze',9,9,
 'Бактерия делится надвое каждый час. Сколько бактерий за 10 часов','Моделирование процесса через ГП','High (Level C)',NULL);

-- ─── П.33: Бесконечно убывающая геометрическая прогрессия (5 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G9_S33_01','L4','G9_P33','Convergence condition','Условие сходимости','Определите, является ли ГП 12, 6, 3, ... бесконечно убывающей',1,'apply',9,9,
 'Определите, является ли ГП 12, 6, 3, ... бесконечно убывающей','Проверка условия |q| < 1','Medium (Level B)','|q|<1'),
('G9_S33_02','L4','G9_P33','Sum of infinite GP','Нахождение суммы бесконечно убывающей ГП','Найдите сумму ГП 4, 2, 1, 1/2, ...',2,'apply',9,9,
 'Найдите сумму ГП 4, 2, 1, 1/2, ...','Применение формулы S = b₁/(1 − q)','Medium (Level B)','S=b₁/(1−q)'),
('G9_S33_03','L4','G9_P33','Repeating decimal','Периодическая дробь как ГП','Представьте 0.333... как сумму бесконечно убывающей ГП',3,'analyze',9,9,
 'Представьте 0.333... как сумму бесконечно убывающей ГП','Определение b₁ и q из десятичной дроби','High (Level C)',NULL),
('G9_S33_04','L4','G9_P33','Find b1 from infinite sum','Нахождение b₁ по сумме бесконечной ГП','Сумма бесконечно убывающей ГП равна 8, q = 1/2. Найдите b₁',4,'analyze',9,9,
 'Сумма бесконечно убывающей ГП равна 8, q = 1/2. Найдите b₁','Выражение b₁ из формулы S = b₁/(1 − q)','High (Level C)',NULL),
('G9_S33_05','L4','G9_P33','Application of infinite GP','Прикладная задача','Мяч падает с высоты 10 м, каждый раз поднимается на 0.6 предыдущей высоты. Найдите общий путь',5,'analyze',9,9,
 'Мяч падает с высоты 10 м, каждый раз поднимается на 0.6 предыдущей высоты. Найдите общий путь','Моделирование через бесконечно убывающую ГП','High (Level C)',NULL);

-- ─── П.34: События (5 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G9_S34_01','L4','G9_P34','Certain event','Достоверное событие','Приведите пример достоверного события',1,'recall',9,9,
 'Приведите пример достоверного события','Понимание определения достоверного события','Low (Level A)',NULL),
('G9_S34_02','L4','G9_P34','Impossible event','Невозможное событие','Приведите пример невозможного события',2,'recall',9,9,
 'Приведите пример невозможного события','Понимание невозможного события','Low (Level A)',NULL),
('G9_S34_03','L4','G9_P34','Random event','Случайное событие','Является ли событие «выпадение числа 4 при бросании кубика» случайным',3,'apply',9,9,
 'Является ли событие «выпадение числа 4 при бросании кубика» случайным','Классификация событий','Medium (Level B)',NULL),
('G9_S34_04','L4','G9_P34','Opposite event','Противоположное событие','Сформулируйте событие, противоположное событию «выпало чётное число»',4,'apply',9,9,
 'Сформулируйте событие, противоположное событию «выпало чётное число»','Определение дополнительного события','Medium (Level B)',NULL),
('G9_S34_05','L4','G9_P34','Compatible events','Совместные события','Являются ли события «число чётное» и «число больше 3» совместными',5,'analyze',9,9,
 'Являются ли события «число чётное» и «число больше 3» совместными','Проверка возможности одновременного наступления','High (Level C)',NULL);

-- ─── П.35: Вероятность события (5 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G9_S35_01','L4','G9_P35','Classical probability','Классическая вероятность','Найдите вероятность выпадения числа 5 при бросании кубика',1,'apply',9,9,
 'Найдите вероятность выпадения числа 5 при бросании кубика','Применение формулы P(A) = m/n','Medium (Level B)','P(A)=m/n'),
('G9_S35_02','L4','G9_P35','Probability of coin','Вероятность при бросании монеты','Какова вероятность выпадения «орла» при бросании монеты',2,'recall',9,9,
 'Какова вероятность выпадения «орла» при бросании монеты','Определение числа благоприятных и возможных исходов','Low (Level A)',NULL),
('G9_S35_03','L4','G9_P35','Even number','Вероятность чётного числа','Найдите вероятность выпадения чётного числа на кубике',3,'apply',9,9,
 'Найдите вероятность выпадения чётного числа на кубике','Подсчёт благоприятных исходов','Medium (Level B)',NULL),
('G9_S35_04','L4','G9_P35','Ball from urn','Вытаскивание шара из урны','В урне 3 белых и 7 красных шаров. Найдите вероятность достать белый',4,'apply',9,9,
 'В урне 3 белых и 7 красных шаров. Найдите вероятность достать белый','Применение формулы к задачам с выбором','Medium (Level B)',NULL),
('G9_S35_05','L4','G9_P35','Probability range','Свойства вероятности','Может ли вероятность события быть равной 1.5',5,'analyze',9,9,
 'Может ли вероятность события быть равной 1.5','Знание ограничений 0 ≤ P(A) ≤ 1','High (Level C)','0≤P(A)≤1');

-- ─── П.36: Относительная частота случайного события (5 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G9_S36_01','L4','G9_P36','Relative frequency definition','Определение относительной частоты','Из 50 бросаний монеты «орёл» выпал 27 раз. Найдите относительную частоту',1,'apply',9,9,
 'Из 50 бросаний монеты «орёл» выпал 27 раз. Найдите относительную частоту','Применение формулы W(A) = M/N','Medium (Level B)','W(A)=M/N'),
('G9_S36_02','L4','G9_P36','Frequency vs probability','Отличие частоты от вероятности','Объясните разницу между вероятностью и относительной частотой',2,'apply',9,9,
 'Объясните разницу между вероятностью и относительной частотой','Понимание теоретической и практической оценки','Medium (Level B)',NULL),
('G9_S36_03','L4','G9_P36','Experiment table','Работа с таблицей эксперимента','По таблице результатов 100 опытов найдите относительную частоту события A',3,'apply',9,9,
 'По таблице результатов 100 опытов найдите относительную частоту события A','Извлечение данных и вычисление частоты','Medium (Level B)',NULL),
('G9_S36_04','L4','G9_P36','Large number of trials','Стабилизация частоты','При 1000 бросаниях «6» выпала 170 раз. Сравните частоту с теоретической вероятностью',4,'analyze',9,9,
 'При 1000 бросаниях «6» выпала 170 раз. Сравните частоту с теоретической вероятностью','Понимание закона больших чисел','High (Level C)',NULL),
('G9_S36_05','L4','G9_P36','Predict by frequency','Прогноз по частоте','Относительная частота дефекта 0.02. Сколько дефектных изделий из 500',5,'analyze',9,9,
 'Относительная частота дефекта 0.02. Сколько дефектных изделий из 500','Применение частоты для прогноза','High (Level C)',NULL);

-- ─── П.37: Случайные величины (5 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G9_S37_01','L4','G9_P37','Identify random variable','Определение случайной величины','Является ли количество очков при бросании кубика случайной величиной',1,'recall',9,9,
 'Является ли количество очков при бросании кубика случайной величиной','Понимание определения случайной величины','Low (Level A)',NULL),
('G9_S37_02','L4','G9_P37','Distribution table','Таблица распределения','Составьте таблицу распределения для числа «орлов» при 2 бросаниях монеты',2,'apply',9,9,
 'Составьте таблицу распределения для числа «орлов» при 2 бросаниях монеты','Перечисление значений и их вероятностей','Medium (Level B)',NULL),
('G9_S37_03','L4','G9_P37','Sum of probabilities','Сумма вероятностей','Проверьте, что сумма вероятностей в таблице равна 1',3,'apply',9,9,
 'Проверьте, что сумма вероятностей в таблице равна 1','Проверка свойства полной группы','Medium (Level B)',NULL),
('G9_S37_04','L4','G9_P37','Expected value from table','Вычисление математического ожидания по таблице','По таблице распределения найдите математическое ожидание',4,'analyze',9,9,
 'По таблице распределения найдите математическое ожидание','Применение формулы M(X) = Σ xᵢpᵢ','High (Level C)','M(X)=Σxᵢpᵢ'),
('G9_S37_05','L4','G9_P37','Interpret random variable','Интерпретация случайной величины','Определите, какие значения может принимать случайная величина «число учеников в классе»',5,'apply',9,9,
 'Определите, какие значения может принимать случайная величина «число учеников в классе»','Определение возможных значений','Medium (Level B)',NULL);

-- ─── П.38: Числовые характеристики случайных величин (6 навыков) ───
INSERT INTO knowledge_hierarchy (id, level, parent_id, name, name_ru, description, sequence_order, cognitive_type, class_level_start, class_level_end, example_task, assessed_ability, difficulty_level, formula)
VALUES
('G9_S38_01','L4','G9_P38','Arithmetic mean of data','Среднее арифметическое','Найдите среднее арифметическое данных 4, 7, 3, 6, 5',1,'apply',9,9,
 'Найдите среднее арифметическое данных 4, 7, 3, 6, 5','Применение формулы среднего','Medium (Level B)','x̄=(x₁+...+xₙ)/n'),
('G9_S38_02','L4','G9_P38','Range of data','Размах данных','Найдите размах данных 3, 7, 2, 9, 5',2,'apply',9,9,
 'Найдите размах данных 3, 7, 2, 9, 5','Нахождение разности наибольшего и наименьшего значений','Medium (Level B)','R=xₘₐₓ−xₘᵢₙ'),
('G9_S38_03','L4','G9_P38','Mode of data set','Мода набора данных','Найдите моду ряда 2, 5, 3, 5, 7, 5, 4',3,'recall',9,9,
 'Найдите моду ряда 2, 5, 3, 5, 7, 5, 4','Определение наиболее часто встречающегося значения','Low (Level A)',NULL),
('G9_S38_04','L4','G9_P38','Median of data','Медиана набора данных','Найдите медиану ряда 1, 3, 5, 7, 9',4,'apply',9,9,
 'Найдите медиану ряда 1, 3, 5, 7, 9','Нахождение центрального элемента','Medium (Level B)',NULL),
('G9_S38_05','L4','G9_P38','All characteristics at once','Комплексный анализ данных','Для набора данных 2, 4, 4, 5, 7, 8, 10 найдите среднее, медиану, моду и размах',5,'analyze',9,9,
 'Для набора данных 2, 4, 4, 5, 7, 8, 10 найдите среднее, медиану, моду и размах','Одновременное вычисление всех характеристик','High (Level C)',NULL),
('G9_S38_06','L4','G9_P38','Compare two data sets','Сравнение двух наборов данных','Сравните два набора данных по среднему и размаху',6,'analyze',9,9,
 'Сравните два набора данных по среднему и размаху','Использование числовых характеристик для анализа','High (Level C)',NULL);
