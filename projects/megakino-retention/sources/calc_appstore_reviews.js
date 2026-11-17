// Воспроизводимый разбор отзывов о приложении «МегаФон» в App Store (id 778681735).
// Запуск: открыть в браузере https://itunes.apple.com/ru/rss/customerreviews/page=1/id=778681735/sortby=mostrecent/json,
// вставить этот файл в консоль разработчика. Имена авторов не сохраняются.
// Ограничение источника: RSS отдаёт только последние ~150 отзывов (10 страниц по 50, фактически меньше).
const RULES = {
  imposed: /(подключа\S*|включа\S*|меня\S*|смени\S*|поменя\S*)[^.!?]{0,50}(без\s+(моего\s+)?(ведом|соглас|спрос|уведом|предупрежд)|не\s+спрос)|без\s+(моего\s+)?(ведома|согласия|спроса)|навяз|сам\S*\s+подключ|подписк[^.!?]{0,40}(без|непойми|молча|задолбал)|списал\S*[^.!?]{0,40}(услуг|опци|ни за что|просто так)|несуществующ\S*\s+опци|по\s*«?\s*шумок/i,
  price: /(повыс|подня|увелич|подорож)\S*[^.!?]{0,40}(плат|цен|стоим|тариф)|(плат|цен|стоим)\S*[^.!?]{0,20}(повыс|подня|увелич)/i,
  support: /\bбот|робот|\bии\b|ии -|поддержк|дозвон|живым|живого опер|с оператором|соедин/i,
  network: /(интернет|связ|5g|инет)\S*[^.!?]{0,40}(не работ|нет\b|пропада|ужас|лага|плох|еле|не грузит|отврат)|не лов|не берет|аварии/i,
  app: /приложени\S*[^.!?]{0,40}(не работ|не заход|крив|ужас|отврат|бесполез|жуть|перестал)|интерфейс|главн\S* экран/i,
  churn_intent: /(перейд|переход|уйду|ухожу|уйти|сменю оператор|поменяю оператор|поменять оператор|на другого оператор|в мтс|на мтс|пора в мтс|в билайн|на билайн|на теле ?2|т2\b|йота)/i,
  video: /кино|кинотеатр|сериал|фильм|\bstart\b|кинопоиск|\bwink\b|\bkion\b|premier/i,
};
(async () => {
  const rev = [];
  for (let p = 1; p <= 10; p++) {
    const r = await fetch(`https://itunes.apple.com/ru/rss/customerreviews/page=${p}/id=778681735/sortby=mostrecent/json`).then(r => r.json()).catch(() => null);
    const e = r?.feed?.entry; if (!e) break;
    for (const x of [].concat(e)) if (x['im:rating']) rev.push({ d: x.updated.label.slice(0, 10), r: +x['im:rating'].label, t: x.title.label, c: x.content.label });
  }
  const rows = rev.map(v => ({ d: v.d, r: v.r, cats: Object.keys(RULES).filter(k => RULES[k].test(v.t + ' ' + v.c)) }));
  const cnt = k => rows.filter(x => x.cats.includes(k)).length;
  const both = (a, b) => rows.filter(x => x.cats.includes(a) && x.cats.includes(b)).length;
  const out = { n: rows.length, from: rows.map(x => x.d).sort()[0], to: rows.map(x => x.d).sort().at(-1), low: rows.filter(x => x.r <= 2).length,
    counts: Object.fromEntries(Object.keys(RULES).map(k => [k, cnt(k)])),
    churn_and_imposed: both('churn_intent', 'imposed'), churn_and_price: both('churn_intent', 'price'),
    churn_and_network: both('churn_intent', 'network'), churn_and_support: both('churn_intent', 'support'),
    none: rows.filter(x => !x.cats.length).length };
  console.log(JSON.stringify(out));
})();
