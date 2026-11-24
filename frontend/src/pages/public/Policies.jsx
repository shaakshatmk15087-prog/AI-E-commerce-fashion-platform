import { Link } from "react-router-dom";

function Page({ title, draft, children }) {
  return (
    <article className="mx-auto max-w-3xl px-4 py-12">
      <h1 className="font-serif text-4xl">{title}</h1>
      {draft && (
        <p role="note" className="mt-4 rounded-xl border border-amber-300 bg-amber-50 p-3 text-sm">
          <strong>Draft for legal review.</strong> This text describes how the platform currently behaves, but it has not been reviewed by a lawyer. Replace the
          [bracketed] details and have it checked against Indian privacy, consumer-protection, tax and e-commerce rules before taking real payments.
        </p>
      )}
      <div className="mt-6 space-y-4 leading-relaxed text-black/80 [&_h2]:mt-8 [&_h2]:font-serif [&_h2]:text-2xl [&_h2]:text-ink [&_ul]:list-disc [&_ul]:pl-6">{children}</div>
    </article>
  );
}

export function Privacy() {
  return (
    <Page title="Privacy Policy" draft>
      <p>Last updated: [date]. [Company legal name] ("we") runs this store, the AI stylist and the stylist-consultation service.</p>
      <h2>What we collect</h2>
      <ul>
        <li><strong>Account:</strong> name, email, optional phone, and a securely hashed password (we never store your password itself).</li>
        <li><strong>Fashion profile (optional):</strong> styles, colours, brands, budget, fit and sizes you choose to give us. We do not infer sensitive attributes from photos.</li>
        <li><strong>Orders:</strong> delivery addresses, items, amounts and payment status. Card details are handled by the payment provider; we never see or store them.</li>
        <li><strong>AI stylist chats:</strong> your messages and our replies, so you can revisit them.</li>
        <li><strong>Consultations:</strong> your booking, notes and the chat with your stylist.</li>
        <li><strong>Wallet and rewards:</strong> a record of credits and points granted, bought, spent or expired.</li>
      </ul>
      <h2>How we use it</h2>
      <p>To run your account, deliver orders, personalise suggestions, connect you with stylists, prevent fraud and meet legal obligations. We do not sell your data.</p>
      <h2>The AI stylist</h2>
      <p>Your chat messages and, where used, relevant fashion-profile details are sent to our AI provider ([provider name]) to generate replies. The AI is only allowed to suggest products from our real catalogue. Replies are labelled as AI-generated. Please don't put sensitive personal information in chats.</p>
      <h2>Who we share it with</h2>
      <p>Payment provider, delivery partners, email provider, the AI provider, hosting providers, and your chosen stylist (only the booking details and chat for your consultation). We share the minimum needed.</p>
      <h2>How long we keep it</h2>
      <ul>
        <li>AI chat history: deleted automatically after [365] days.</li>
        <li>Orders, payments and credit/points records: kept as required for accounting and legal purposes, [number] years.</li>
        <li>Everything else: until you delete your account.</li>
      </ul>
      <h2>Your choices and rights</h2>
      <p>In <Link className="underline" to="/account">Account → Privacy &amp; data</Link> you can download a copy of your data and permanently delete your account. Deleting removes your name, email, phone, addresses, fashion profile, wishlist and AI chats; records we must keep (orders, payments, ledgers) stay but are no longer linked to you. Remaining credits, points and any subscription are forfeited. You can also edit or delete your fashion profile at any time.</p>
      <h2>Security</h2>
      <p>Connections are encrypted, passwords are hashed, access is restricted by role, and sensitive administrator actions are logged. No system is perfectly secure; tell us at once if you suspect a problem.</p>
      <h2>Contact</h2>
      <p>[Grievance/privacy officer name], [email], [postal address].</p>
    </Page>
  );
}

export function Terms() {
  return (
    <Page title="Terms and Conditions" draft>
      <p>Last updated: [date]. By creating an account or buying from [Company legal name] you agree to these terms.</p>
      <h2>Accounts</h2>
      <p>You must give accurate details, keep your password secret, and be at least [18] years old. We may suspend accounts used for fraud or abuse.</p>
      <h2>Products and prices</h2>
      <p>Prices and availability are shown on each product page and confirmed again at checkout. An order is confirmed only after your payment is verified.</p>
      <h2>AI stylist</h2>
      <p>The AI stylist suggests products from our catalogue to help you choose. Suggestions are not professional advice and may be imperfect; always check the product details before buying.</p>
      <h2>Credits</h2>
      <ul>
        <li><strong>Daily Credits</strong> are a free allowance that expires at the daily reset shown in your wallet. They cannot be transferred.</li>
        <li><strong>Super Credits</strong> are bought or earned through a subscription, do not expire, and cannot be transferred or exchanged for money.</li>
        <li>The cost of each service is shown before you confirm. Credits have no cash value.</li>
      </ul>
      <h2>Stylist consultations</h2>
      <p>Booking holds the credit cost. Cancellation and refund rules are shown before you book (currently: free cancellation until [24] hours before the session, [50]% refunded after that, full refund if the stylist declines, cancels or doesn't respond). Stylists are independent professionals; their advice is their own.</p>
      <h2>Subscriptions</h2>
      <p>A plan runs for the paid period and adds the Super Credits described on the plan. Renewal is a separate payment. Cancelling keeps your access until the period ends; paid periods are not refunded unless required by law.</p>
      <h2>Rewards</h2>
      <p>Reward points are earned on delivered, paid orders and qualifying referrals, can be redeemed only for the offers shown, have no cash value, and may be reversed if the related order is refunded. Abuse (such as fake referrals) voids rewards.</p>
      <h2>Liability and changes</h2>
      <p>[Limitation of liability, governing law and jurisdiction.] We may update these terms and will tell you about material changes.</p>
      <h2>Contact</h2>
      <p>[Email], [address].</p>
    </Page>
  );
}

export function Returns() {
  return (
    <Page title="Returns and Refund Policy" draft>
      <p>Last updated: [date].</p>
      <h2>Returns</h2>
      <p>Products marked "eligible for return" can be returned within [7] days of delivery if unused and in original condition. Some items (for example innerwear or customised items) are not returnable and are marked on the product page. To start a return, contact us at [email] with your order number.</p>
      <h2>Refunds</h2>
      <ul>
        <li>Approved refunds go back to your original payment method within [5–7] business days.</li>
        <li>If we cancel an order or can't fulfil it, you get a full refund.</li>
        <li>If an order is cancelled before payment completes, nothing is charged and reserved stock is released.</li>
      </ul>
      <h2>Credits, subscriptions and consultations</h2>
      <ul>
        <li>Consultation credits are returned according to the cancellation rules shown when you book.</li>
        <li>Super Credit packs and subscription payments are not refundable except where required by law.</li>
        <li>Rewards points earned on a refunded order are removed.</li>
      </ul>
      <h2>Contact</h2>
      <p>[Support email], [phone], [hours].</p>
    </Page>
  );
}

export function About() {
  return (
    <Page title="About">
      <p>AI Fashion is a conversational fashion store. Tell our AI stylist about an occasion, a budget or a colour you love and it suggests real, in-stock products. When you want a human opinion, book a text consultation with a professional stylist.</p>
      <p>We keep AI suggestions separate from verified facts: every price, size and availability you see comes straight from our catalogue, and AI-generated text is always labelled.</p>
      <p><Link className="underline" to="/shop">Browse the shop</Link> · <Link className="underline" to="/ai-stylist">Talk to the AI stylist</Link> · <Link className="underline" to="/stylists">Consult a stylist</Link></p>
    </Page>
  );
}

const FAQ = [
  ["What are Daily Credits and Super Credits?", "Daily Credits are a free allowance that resets every day (unused ones expire). Super Credits are bought or come with a subscription, never expire and add up. Your wallet always shows them separately."],
  ["Does the AI stylist cost credits?", "Your wallet's \"What credits are used for\" section always shows the current cost. When a message costs credits you are only charged if the AI actually gives you recommendations."],
  ["Is the AI stylist always right?", "It can make mistakes, which is why it can only suggest products that really exist and are in stock, and why prices always come from the shop, not the AI."],
  ["How do consultations work?", "Pick a stylist and a time, see the exact credit cost, and confirm. The stylist accepts, you chat in text, and they mark the session complete. Cancellation rules are shown before you book."],
  ["How do I get my money back?", "See the Returns and Refund Policy. For orders, contact us with your order number."],
  ["How do rewards work?", "You earn points on orders once they are delivered, and bonus points when a friend you refer gets their first order delivered. Points can be redeemed for Super Credits."],
  ["Can I delete my account or download my data?", "Yes: Account → Privacy & data."],
];

export function Faq() {
  return (
    <Page title="Help / FAQ">
      <dl className="space-y-5">{FAQ.map(([q, a]) => <div key={q}><dt className="font-medium text-ink">{q}</dt><dd className="mt-1">{a}</dd></div>)}</dl>
      <p>Still stuck? <Link className="underline" to="/contact">Contact us</Link>.</p>
    </Page>
  );
}

export function Contact() {
  return (
    <Page title="Contact">
      <p>[Support email] · [phone] · [hours]</p>
      <p>[Registered address]</p>
      <p>Please include your order number for order questions. For privacy requests use <Link className="underline" to="/account">Account → Privacy &amp; data</Link> or write to [privacy contact].</p>
    </Page>
  );
}
