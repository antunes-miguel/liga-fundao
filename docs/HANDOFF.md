# Fantasy Fundão: redesign (handoff)

> **Para o Claude que pegar nisto:** lê este ficheiro todo antes de mexer no `index.html`.
> É um protótipo funcional desenhado pelo João, com dados reais da J10 tirados do site atual,
> e algumas partes com dados de exemplo (lista na secção 4). O objetivo é ligá-lo ao pipeline
> de dados que o site atual (`antunes-miguel.github.io`) já tem, sem desfazer as decisões de
> design da secção 6.

---

## 1. O que está na pasta

| Ficheiro | O que é |
|---|---|
| `index.html` | A app inteira: HTML, CSS e JS sem dependências nem build. Fotos embutidas em base64. |
| `manifest.webmanifest` | Instalação como app (nome "Fundão" no ecrã principal, arranca em `#jornada`). |
| `icons/` | Ícones gerados a partir do escudo e das riscas da marca: 180 (iPhone), 192, 512, maskable 512 (Android), favicon 32. |
| `HANDOFF.md` | Este ficheiro. |

Marca: Figma `TSLGt00PdVzXsy60hWoqFn`, secção "Final 1" (paleta "Cherry to Forest", tipografia, stickers, wallpapers).

---

## 2. Estrutura do produto

```
Jornada  (#jornada / #liga)
 ├─ Cartão da jornada: setas para mudar de jornada, partilhar, vencedor + sticker 1.º Lugar,
 │  💰 Pote, último lugar (sticker grande + cara pequena), ícone secundário da marca no canto
 ├─ Painel com seletor  Jornada | Geral  + botão de partilhar a tabela visível
 │    · Jornada: pontos e quanto cada um paga nessa jornada
 │    · Geral: classificação depois da jornada escolhida no cartão
 ├─ Botão de notificações (2 estados)
 └─ Rodapé: custo por ponto e data da última atualização

Insights (#insights)
 └─ Forma · Evolução · Capitães · Banco · Chips · Onzes   (+ partilhar a vista, + 1 linha de explicação)

Perfil (#jogador-<id>, ex. #jogador-tm)  ← abre a partir de qualquer linha de jogador
 ├─ Cartão: foto, sticker se 1.º/último, lugar, pontos, "para subir", pago/deve
 ├─ Jornada a jornada (barras + melhor da jornada + lugar)
 ├─ Dívida: total, grelha por jornada (pago/por pagar), histórico de pagamentos, partilhar
 └─ Época: vitórias, melhor jornada, capitão, banco, chips, onze mais parecido
```

- Telemóvel: barra de navegação em vidro em baixo (Jornada, Insights), que encolhe ao fazer scroll. O cabeçalho, ao fazer scroll, fica só com dois botões de vidro: o escudo e o tema.
- Desktop: navegação no cabeçalho. O cartão e o painel das tabelas têm sempre a mesma altura.
- Temas: Automático, Claro ou Escuro, guardado em `localStorage` (`ff-theme`).

---

## 3. Dados: estruturas e de onde vêm na API da FPL

Todas as estruturas estão no topo do `<script>` (procurar `═════════ Data`). O resto da app só lê destas.

| Estrutura | Forma | Origem na API da FPL |
|---|---|---|
| `NGW` | jornada atual (número) | `bootstrap-static` → `events[]` com `finished`/`is_current` |
| `COST` | `0.10` | regra da liga |
| `PLAYERS` | `[{id, name, short}]` | `leagues-classic/{id}/standings` → `player_name`. `short` = primeiro nome, ou nome + inicial do apelido quando há nomes repetidos (Diogo L., João P.). |
| `NET[id][gw-1]` | pontos líquidos por jornada | `entry/{id}/history` → `current[].points − current[].event_transfers_cost` |
| `HITS[gw][id]` | custo de transferências | `current[].event_transfers_cost` |
| `CHIPS[id]` | `{WC, BB, TC, FH: jornada}` | `history` → `chips[]` (`wildcard`, `bboost`, `3xc`, `freehit`) |
| `BENCH[id]` | `{gw, worst:[pts, gw], total}` | `current[].points_on_bench`, **excluindo jornadas com Bench Boost** |
| `CAPS[id]` | `{cap, pts, tc, right, lost, eff}` | `entry/{id}/event/{gw}/picks` (capitão, multiplicador) + `event/{gw}/live` (pontos de cada jogador) |
| `XI[id]` | 11 nomes da última jornada | `picks[]` com `position` 1 a 11, antes das substituições automáticas |
| `PAGAMENTOS[id]` | `[{data:'AAAA-MM-DD', valor}]` | **não vem da FPL.** O Miguel mantém isto à mão (sugestão: `pagamentos.json` no repositório). |
| `AVATARS[id]` | data URI 192×192 | fotos enviadas pelo João (ver secção 5) |

**Regras de cálculo (iguais às do site atual):**
- Dívida da jornada = `(melhor pontuação líquida − pontuação líquida) × COST`. O melhor não paga. Com empate no topo, nenhum dos empatados paga.
- **Capitães:** eficiência = pontos do capitão ÷ pontos do melhor jogador do onze, somados na época. Acertos = jornadas em que o capitão foi o melhor. Perdidos = pontos que a braçadeira deixou de ganhar (o site atual conta ×2 no Triple Captain; manter igual). Se o capitão não jogou, conta o vice.
- **Pagamentos:** cada pagamento abate as jornadas mais antigas primeiro (`coverage()`). Por isso basta registar data e valor. Pagamentos a mais aparecem como "a favor".
- **Desempate na classificação:** menos transferências, depois ordem alfabética. ⚠ `order()` só aplica a ordem alfabética, porque o protótipo não tem o total de transferências. Somar `current[].event_transfers` e acrescentar ao `sort`.

**CORS:** a API da FPL não aceita pedidos diretos do browser. O site atual já vai buscar estes dados de alguma forma. Manter esse pipeline (por exemplo, um job agendado que escreve um `data.json`) e preencher estas estruturas a partir dele.

---

## 4. ⚠ Dados de exemplo e valores fixos: trocar antes de publicar

| O quê | Onde | Estado |
|---|---|---|
| Onzes de todos menos o Bernardo | `XI` | **Inventado.** Só o onze do Bernardo e o que cada um tem em comum com ele são reais. Afeta a vista Onzes e "Onze mais parecido" no perfil. |
| Pagamentos | `PAGAMENTOS` | **Inventado** (1 set, 1 out, 2 nov, 10 nov; J10 por pagar para o João P. e o Tiago). O site atual diz que está tudo pago. |
| Custos de transferências | `HITS` | Só a J10 é conhecida (Bernardo −4, António −4). |
| "Atualizado a 9 nov às 15:02" | rodapé (`#foot-updated`) | Texto fixo. Ligar à data dos dados. |
| Capitães, banco, chips | `CAPS`, `BENCH`, `CHIPS` | Reais, copiados do site atual na J10. |
| Fotos | `AVATARS` | Reais. Ver privacidade na secção 5. |

---

## 5. O que falta ligar no produto real

1. **Dados:** substituir as constantes pelos dados do pipeline (secção 3). Tudo é calculado a partir delas.
2. **Notificações** (`#notif`): hoje só muda de estado visual. Falta:
   - pedir permissão (`Notification.requestPermission`);
   - registar um service worker e criar a subscrição push (VAPID);
   - guardar a subscrição e enviar quando a jornada fecha.

   No iPhone só funciona com a app adicionada ao ecrã principal (iOS 16.4 ou mais recente).
3. **Fotos:** passar de base64 para ficheiros (`avatars/<id>.jpg`) para o HTML ficar leve. O site está no GitHub Pages, que é público: confirmar com o grupo que estão OK com as caras visíveis.
4. **Tipo de letra:** a marca usa "Premier League Bold", que é licenciada. O CSS já a pede primeiro (`--display`) e usa Lexend como alternativa. Se houver licença, adicionar o `@font-face`. O texto corrido é Inter (Google Fonts).
5. **Partilhar imagens:** usa a Web Share API com ficheiros, e "Guardar imagem" onde isso não existe. Só se testa a sério com o site publicado num endereço `https`.
6. **Chips:** a grelha assume dois de cada chip por época (um por metade) e mostra a 1.ª metade. Quando a 2.ª metade abrir, `CHIPS[id][chip]` tem de passar a aceitar duas jornadas.
7. **Estados em falta:** a carregar, API em baixo, jornada a decorrer (pontos ao vivo via `event/{gw}/live`) e início de época sem dados.
8. **Offline (opcional):** não há service worker. Se for criado para as notificações, pode também guardar a última versão dos dados.

---

## 6. Decisões de design: não desfazer sem falar com o João

- **Só dois separadores** (Jornada, Insights). A Liga vive no seletor Jornada | Geral. Os perfis abrem por cima do primeiro separador.
- **Sem texto de enchimento.** Nada de explicações redundantes, contas repetidas ("79 − 4 transf.") ou barras que só repetem números. Nos Insights há uma única linha de explicação por vista, por baixo.
- **Linhas de jogador são `<button data-player>`** com navegação em JS (`go()`, `show()`), e não `<a href="#…">`. Os links eram bloqueados em pré-visualizações em iframe. O endereço continua a refletir a vista via `history.pushState` quando o browser deixa.
- **A lista da Geral tem `id="tabela-geral"`** e não `liga`. Um id igual ao hash fazia a página saltar ao abrir `#liga`.
- **Telemóveis estreitos:** abaixo de 480px as tabelas usam nomes curtos, para nada partir em duas linhas.
- **Pontos a verde da marca:** Forest no claro, #80CC80 no escuro. Euros a branco ou texto, "por pagar" a cereja.
- **Stickers** "1.º Lugar" e "Último Lugar 💩" recriados em SVG a partir do Figma.
  - O último lugar é o espelho do vencedor: sticker grande e cara pequena, alinhado à direita.
  - No rodapé do cartão, "💰 POTE" e o nome do último estão na mesma linha, e os dois valores também (medido no browser).
- **Cartão e painel das tabelas com a mesma altura no desktop:** o cartão estica. O Pote e o último lugar ficam em baixo; o vencedor fica em cima.
- **Vidro "Liquid Glass"** na barra de baixo, no seletor do desktop e no cabeçalho ao fazer scroll. Sem refração, porque o Safari não suporta o filtro SVG necessário.
- **Imagens de partilha (1080×1350)** desenhadas em canvas, de propósito, e não com html2canvas: este não suporta `color-mix()` e o vidro. Todas usam a mesma moldura (`frameImage`).
- **Cores:** tokens em `:root`. O escuro está escrito duas vezes, para o sistema (`prefers-color-scheme`) e para a escolha manual (`[data-theme]`).
  - O texto cereja no escuro é #E07A8B, mais claro que a marca, por contraste; o #8B2D3A da marca fica só em formas.
  - No heatmap, os números passam a branco só quando a célula é forte.

---

## 7. Verificações feitas antes da entrega

- Todas as vistas e os 9 perfis a 320, 390 e 1280px, nos dois temas: nenhuma página com scroll horizontal.
- Todos os botões têm nome acessível e todas as imagens têm `alt`.
- As 9 imagens de partilha geram sem erros: jornada, geral, dívida e as 6 dos Insights.
- Contas conferidas com o site atual: totais de pontos (687 … 484), pago por pessoa (10,40 € … 30,70 €), pote 159,40 € e setas de subida/descida da J9 para a J10.
- Pagamentos: para os 9, pago + em falta = total da época. Testado também com pagamento parcial e pagamento a mais.
- Navegação, perfis e partilha também a funcionar dentro de um iframe com `sandbox="allow-scripts"`.
- Nenhum erro na consola. A única falha de rede no ambiente de teste foi o Google Fonts, que estava sem internet.

**Para voltar a testar:** abrir `index.html`, percorrer Jornada → Geral → um perfil → voltar → Insights (6 vistas) → partilhar cada uma. Repetir em Claro e Escuro, e mudar de jornada com as setas do cartão.
